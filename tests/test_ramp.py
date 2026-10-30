"""Unit tests for the pure setpoint ramp logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.vtherm_gentle_start.const import COMMAND_CAUSE_UNDERLYING_TRACKING
from custom_components.vtherm_gentle_start.ramp import (
    ACTION_DOWN,
    ACTION_HOLD,
    ACTION_REACHED,
    ACTION_START,
    ACTION_UP,
    SetpointRamp,
    effective_step,
    is_ramp_mode,
    round_to_nearest,
)

CYCLE_SECONDS = 300
START = datetime(2026, 1, 1, 8, 0, tzinfo=timezone.utc)


class Clock:
    """A simulated clock which moves by whole cycles."""

    def __init__(self) -> None:
        self.now = START

    def next_cycle(self) -> datetime:
        """Move forward by one cycle."""
        self.now += timedelta(seconds=CYCLE_SECONDS)
        return self.now


def adjust(
    ramp: SetpointRamp,
    now: datetime,
    desired: float,
    *,
    mode="heat",
    room: float | None = 18.0,
    offset=-0.5,
    max_step=1.0,
    step=0.5,
    cause=None,
    slope=None,
    target=None,
    horizon=None,
) -> float:
    """Call the ramp with the usual arguments. The slope is in degrees per hour, so 6 is half a degree per cycle."""
    return ramp.adjust(
        desired,
        step,
        cause,
        mode=mode,
        current_temperature=room,
        now=now,
        cycle_seconds=CYCLE_SECONDS,
        start_offset=offset,
        max_step=max_step,
        target=target,
        slope_per_hour=slope,
        horizon_seconds=horizon,
    )


def run(ramp: SetpointRamp, clock: Clock, desired: float, cycles: int, **kwargs) -> list[float]:
    """Run the start and some cycles, and return what is sent each time."""
    sent = [adjust(ramp, clock.now, desired, **kwargs)]
    for _ in range(cycles):
        sent.append(adjust(ramp, clock.next_cycle(), desired, **kwargs))
    return sent


@pytest.mark.parametrize(
    "room, target, offset, max_step, step, expected",
    [
        # A negative offset starts below the room temperature: the unit sees no demand at first
        (18, 21, -0.5, 1.0, 0.5, [17.5, 18.5, 19.5, 20.5, 21, 21]),
        # A positive offset starts above the room temperature
        (18, 21, 1.0, 0.5, 0.5, [19, 19.5, 20, 20.5, 21, 21]),
        # Zero starts at the room temperature
        (18, 21, 0.0, 1.0, 0.5, [18, 19, 20, 21, 21]),
        # The start never goes beyond the target
        (20, 21, 1.5, 1.0, 0.5, [21, 21]),
        # No limit per cycle: the target is sent on the first cycle after the start
        (18, 21, -1.0, 0.0, 0.5, [17, 21, 21]),
    ],
)
def test_heat_sequence(room, target, offset, max_step, step, expected) -> None:
    """The setpoint starts relative to the room temperature, then moves by at most one step per cycle."""
    sent = run(SetpointRamp(), Clock(), target, len(expected) - 1, room=room, offset=offset, max_step=max_step, step=step)
    assert sent == expected


@pytest.mark.parametrize(
    "room, target, offset, max_step, expected",
    [
        # Cooling is the mirror of heating: a negative offset starts above the room temperature
        (26, 23, -0.5, 1.0, [26.5, 25.5, 24.5, 23.5, 23, 23]),
        # A positive offset starts below the room temperature
        (26, 23, 1.0, 0.5, [25, 24.5, 24, 23.5, 23, 23]),
    ],
)
def test_cool_sequence(room, target, offset, max_step, expected) -> None:
    """In cool mode the setpoint goes down, never below the target."""
    sent = run(SetpointRamp(), Clock(), target, len(expected) - 1, mode="cool", room=room, offset=offset, max_step=max_step)
    assert sent == expected


def test_step_only_once_per_cycle() -> None:
    """Several regulations within one cycle move the setpoint once."""
    ramp = SetpointRamp()
    clock = Clock()
    assert adjust(ramp, clock.now, 21) == 17.5
    # A second later and half a cycle later: still the start setpoint
    assert adjust(ramp, clock.now + timedelta(seconds=1), 21) == 17.5
    assert adjust(ramp, clock.now + timedelta(seconds=CYCLE_SECONDS / 2), 21) == 17.5
    # A little before the whole cycle (a tick can come early) the step is due
    assert adjust(ramp, clock.now + timedelta(seconds=CYCLE_SECONDS - 1), 21) == 18.5


def test_target_raised_continues_the_ramp() -> None:
    """A higher target does not restart the ramp, it moves by one step per cycle."""
    ramp = SetpointRamp()
    clock = Clock()
    assert run(ramp, clock, 19, 3) == [17.5, 18.5, 19, 19]
    assert adjust(ramp, clock.next_cycle(), 23) == 20
    assert adjust(ramp, clock.next_cycle(), 23) == 21


def test_target_lowered_is_sent_at_once() -> None:
    """A change which reduces the demand is not limited."""
    ramp = SetpointRamp()
    clock = Clock()
    run(ramp, clock, 21, 2)
    assert ramp.value == 19.5
    assert adjust(ramp, clock.now, 18.5) == 18.5
    assert ramp.value == 18.5
    assert ramp.action == ACTION_DOWN


def test_reset_starts_a_new_ramp() -> None:
    """After a reset (the thermostat was off) the ramp starts again from the room temperature."""
    ramp = SetpointRamp()
    clock = Clock()
    run(ramp, clock, 21, 3)
    ramp.reset()
    assert ramp.value is None
    assert adjust(ramp, clock.next_cycle(), 21, room=19.0) == 18.5


def test_mode_switch_starts_a_new_ramp() -> None:
    """Heating becomes cooling: the ramp starts again in the other direction."""
    ramp = SetpointRamp()
    clock = Clock()
    run(ramp, clock, 21, 2)
    assert adjust(ramp, clock.next_cycle(), 24, mode="cool", room=26.0) == 26.5


def test_underlying_tracking_is_not_ramped() -> None:
    """A change made on the device is followed as it is, and the ramp continues from there."""
    ramp = SetpointRamp()
    clock = Clock()
    assert adjust(ramp, clock.now, 21, cause=COMMAND_CAUSE_UNDERLYING_TRACKING) == 21
    assert ramp.value == 21
    assert adjust(ramp, clock.next_cycle(), 21) == 21


def test_restore_resumes_the_ramp() -> None:
    """After a restart the ramp resumes from the restored position and waits a whole cycle for its next step."""
    ramp = SetpointRamp()
    clock = Clock()
    ramp.restore(19.5)
    assert adjust(ramp, clock.now, 21) == 19.5
    assert adjust(ramp, clock.next_cycle(), 21) == 20.5


def test_restore_survives_a_reset() -> None:
    """The thermostat can look off for a moment at startup: the restored position is kept."""
    ramp = SetpointRamp()
    ramp.restore(19.5)
    ramp.reset()
    assert adjust(ramp, START, 21) == 19.5


def test_no_room_temperature_returns_the_desired_setpoint() -> None:
    """Without the room temperature there is nothing to start from, and no ramp is started."""
    ramp = SetpointRamp()
    assert adjust(ramp, START, 21, room=None) == 21
    assert ramp.value is None


def test_step_is_not_below_the_regulation_step() -> None:
    """A step below the rounding step would be cancelled by the rounding: the regulation step is used."""
    assert effective_step(0.2, 0.5) == (0.5, True)
    assert effective_step(1.0, 0.5) == (1.0, False)
    assert effective_step(0.0, 0.5) == (0.0, False)
    sent = run(SetpointRamp(), Clock(), 20, 3, room=18.0, offset=-0.5, max_step=0.2, step=0.5)
    assert sent == [17.5, 18.0, 18.5, 19.0]


def test_helpers() -> None:
    """The rounding and the mode check."""
    assert round_to_nearest(17.74, 0.5) == 17.5
    assert round_to_nearest(17.76, 0.5) == 18.0
    assert round_to_nearest(17.76, 0) == 17.76
    assert is_ramp_mode("heat") and is_ramp_mode("cool")
    assert not is_ramp_mode("off") and not is_ramp_mode(None)


def started(clock: Clock, desired: float = 21.0, cycles: int = 0, warm: bool = True, **kwargs) -> SetpointRamp:
    """A ramp which has started and run some cycles. The clock is on the last one.

    The slope of the room temperature is ignored during the first cycles of a ramp: unless ``warm`` is False the ramp is made to look as
    if it had started long ago.
    """
    ramp = SetpointRamp()
    run(ramp, clock, desired, cycles, **kwargs)
    if warm:
        ramp._started_at = START - timedelta(days=1)  # pylint: disable=protected-access
    return ramp


def test_actions() -> None:
    """The ramp says what it did at its last decision."""
    ramp = SetpointRamp()
    clock = Clock()
    assert ramp.action is None
    adjust(ramp, clock.now, 18.5)
    assert ramp.action == ACTION_START
    adjust(ramp, clock.next_cycle(), 18.5)
    assert (ramp.value, ramp.action) == (18.5, ACTION_UP)
    adjust(ramp, clock.next_cycle(), 18.5)
    assert (ramp.value, ramp.action) == (18.5, ACTION_REACHED)
    ramp.reset()
    assert ramp.action is None


def test_rising_room_that_stays_below_the_target_does_not_slow_the_ramp() -> None:
    """A prediction below the target changes nothing: the setpoint rises by one step per cycle."""
    clock = Clock()
    ramp = started(clock)
    # 19 + 0.5 = 19.5, below 21
    assert adjust(ramp, clock.next_cycle(), 21, room=19.0, slope=6.0) == 18.5
    assert ramp.action == ACTION_UP


def test_room_predicted_just_past_the_target_holds_the_setpoint() -> None:
    """A room which would be a little past the target by the next decision stops the setpoint from rising."""
    clock = Clock()
    ramp = started(clock)
    # 20.8 + 0.5 = 21.3: 0.3 past the target, less than a regulation step
    assert adjust(ramp, clock.next_cycle(), 21, room=20.8, slope=6.0) == 17.5
    assert ramp.action == ACTION_HOLD
    # The room has slowed down: the ramp moves again
    assert adjust(ramp, clock.next_cycle(), 21, room=20.9, slope=0.0) == 18.5
    assert ramp.action == ACTION_UP


def test_room_predicted_well_past_the_target_lowers_the_setpoint() -> None:
    """A room which would be a whole regulation step or more past the target gets a lower setpoint, by one step."""
    clock = Clock()
    ramp = started(clock, cycles=4, room=18.0)
    assert ramp.value == 21
    # 21 + 1 = 22: 1 past the target. One step down is 20, the gentlest level is 20.5 (room 21 - 0.5 offset)
    assert adjust(ramp, clock.next_cycle(), 21, room=21.0, slope=12.0) == 20.5
    assert ramp.action == ACTION_DOWN
    # Still predicted past the target: the setpoint is already at the gentlest level
    assert adjust(ramp, clock.next_cycle(), 21, room=21.0, slope=12.0) == 20.5
    assert ramp.action == ACTION_HOLD
    # The room cools: the setpoint goes back to the desired one
    assert adjust(ramp, clock.next_cycle(), 21, room=20.9, slope=-3.0) == 21
    assert ramp.action == ACTION_UP


@pytest.mark.parametrize(
    "offset, expected",
    [
        # The gentlest level is the room temperature plus a negative offset
        (-0.5, 20.0),
        # A positive offset is for the start only: the setpoint is never lowered below the room temperature
        (1.0, 20.5),
    ],
)
def test_lowered_setpoint_stops_at_the_gentlest_level(offset, expected) -> None:
    """Lowering the demand goes no further than the room temperature plus a negative start offset."""
    clock = Clock()
    ramp = started(clock, cycles=1, room=20.5, offset=offset)
    assert ramp.value == 21
    assert adjust(ramp, clock.next_cycle(), 21, room=20.5, offset=offset, slope=18.0) == expected


def test_cooling_mirrors_heating() -> None:
    """In cool mode the room falls towards the target, and the setpoint is raised to ease the demand."""
    clock = Clock()
    ramp = started(clock, 23.0, cycles=4, mode="cool", room=26.0)
    assert ramp.value == 23
    # 23 - 1 = 22: 1 past the target. One step up is 24, the gentlest level is 23.5 (room 23 + 0.5)
    assert adjust(ramp, clock.next_cycle(), 23, mode="cool", room=23.0, slope=-12.0) == 23.5
    assert ramp.action == ACTION_DOWN
    # 24 - 0.5 = 23.5 is not below the target: the setpoint goes back to the desired one
    assert adjust(ramp, clock.next_cycle(), 23, mode="cool", room=24.0, slope=-6.0) == 23.0
    assert ramp.action == ACTION_UP


def test_cooling_holds_for_a_small_overshoot() -> None:
    """A small predicted overshoot in cool mode holds the setpoint."""
    clock = Clock()
    ramp = started(clock, 23.0, mode="cool", room=26.0)
    assert ramp.value == 26.5
    # 23.2 - 0.5 = 22.7: 0.3 past the target
    assert adjust(ramp, clock.next_cycle(), 23, mode="cool", room=23.2, slope=-6.0) == 26.5
    assert ramp.action == ACTION_HOLD


def test_the_target_of_the_thermostat_is_the_limit_not_the_desired_setpoint() -> None:
    """The self-regulation can ask for more than the target: the room must still not pass the target."""
    clock = Clock()
    ramp = started(clock, 22.0)
    # 20.4 + 0.5 = 20.9, below the target of 21: the ramp rises
    assert adjust(ramp, clock.next_cycle(), 22, room=20.4, slope=6.0, target=21.0) == 18.5
    # 20.9 + 0.5 = 21.4 is past the target of 21 although it is below the desired 22
    assert adjust(ramp, clock.next_cycle(), 22, room=20.9, slope=6.0, target=21.0) == 18.5
    assert ramp.action == ACTION_HOLD
    # Without the target of the thermostat the desired setpoint is the limit
    assert adjust(ramp, clock.next_cycle(), 22, room=20.9, slope=6.0) == 19.5
    assert ramp.action == ACTION_UP


def test_the_ramp_never_goes_above_the_desired_setpoint() -> None:
    """Easing and holding only lower the setpoint: the desired setpoint stays the upper bound."""
    clock = Clock()
    ramp = started(clock, 21.0, cycles=4)
    assert adjust(ramp, clock.next_cycle(), 20.0, room=19.0, slope=-6.0) == 20.0
    assert adjust(ramp, clock.next_cycle(), 20.0, room=19.0, slope=-6.0) == 20.0


def test_unknown_slope_or_room_changes_nothing() -> None:
    """Without a slope the ramp is the plain ramp."""
    clock = Clock()
    ramp = started(clock)
    assert adjust(ramp, clock.next_cycle(), 21, room=20.9, slope=None) == 18.5
    assert adjust(ramp, clock.next_cycle(), 21, room=None, slope=30.0) == 19.5


def test_a_late_decision_looks_as_far_ahead_as_it_waited() -> None:
    """A missed tick doubles the time to the next decision, so the room is predicted twice as far."""
    # One cycle: 20.4 + 0.5 = 20.9, below the target
    clock = Clock()
    ramp = started(clock)
    assert adjust(ramp, clock.next_cycle(), 21, room=20.4, slope=6.0) == 18.5
    # Two cycles since the last decision: 20.4 + 1.0 = 21.4, past the target
    clock = Clock()
    ramp = started(clock)
    clock.next_cycle()
    assert adjust(ramp, clock.next_cycle(), 21, room=20.4, slope=6.0) == 17.5
    assert ramp.action == ACTION_HOLD


def test_the_look_ahead_is_capped() -> None:
    """A long silence does not make the look-ahead grow without limit."""
    ramp = SetpointRamp()
    assert adjust(ramp, START, 21) == 17.5
    # An hour later the look-ahead is two cycles (10 minutes): 20.4 + 3 / 6 = 20.9, below the target
    assert adjust(ramp, START + timedelta(hours=1), 21, room=20.4, slope=3.0) == 18.5


def test_given_horizon_is_used() -> None:
    """The look-ahead is the time to the next decision, which can be a regulation period longer than a cycle."""
    ramp = SetpointRamp()
    assert adjust(ramp, START, 21, horizon=900) == 17.5
    # 15 minutes: 20.4 + 1.5 = 21.9, past the target
    assert adjust(ramp, START + timedelta(seconds=900), 21, room=20.4, slope=6.0, horizon=900) == 17.5


def test_unlimited_step_is_lowered_by_the_regulation_step() -> None:
    """With no limit per cycle, the setpoint is lowered by one regulation step."""
    clock = Clock()
    ramp = started(clock, cycles=1, room=20.0, max_step=0.0, step=0.1)
    assert ramp.value == 21
    assert adjust(ramp, clock.next_cycle(), 21, room=21.0, max_step=0.0, step=0.1, slope=12.0) == 20.9


def test_tracking_clears_the_action() -> None:
    """A change made on the device is followed, and the ramp has no action to report."""
    ramp = SetpointRamp()
    adjust(ramp, START, 21, cause=COMMAND_CAUSE_UNDERLYING_TRACKING)
    assert ramp.action is None


def test_the_slope_is_ignored_during_the_first_cycles_of_a_ramp() -> None:
    """Right after a start the slope still describes the room before the heating: it is used from the second cycle."""
    clock = Clock()
    ramp = started(clock, warm=False)
    # A slope which would hold the setpoint: 20.8 + 0.5 = 21.3, past the target
    assert adjust(ramp, clock.next_cycle(), 21, room=20.8, slope=6.0) == 18.5
    assert ramp.action == ACTION_UP
    assert adjust(ramp, clock.next_cycle(), 21, room=20.8, slope=6.0) == 18.5
    assert ramp.action == ACTION_HOLD


def test_the_slope_is_ignored_again_after_the_ramp_follows_the_device() -> None:
    """A change made on the device restarts the ramp, and the slope is ignored for two cycles again."""
    clock = Clock()
    ramp = started(clock, cycles=4)
    adjust(ramp, clock.next_cycle(), 22, cause=COMMAND_CAUSE_UNDERLYING_TRACKING)
    assert adjust(ramp, clock.next_cycle(), 23, room=22.8, slope=12.0) == 23
    assert ramp.action == ACTION_UP


# Heating and cooling are one logic with a direction. Run the same scenario in both modes, with the room, the target, the regulated
# temperature and the slope inverted around an axis, and the ramp must answer with the inverted setpoints and the same actions.
MIRROR = 44.0
TRACKING = COMMAND_CAUSE_UNDERLYING_TRACKING

# (room, slope in degrees per hour, regulated temperature, target, cause). The slope is ignored during the first two cycles.
HEATING_SCENARIOS = {
    # The room rises, the setpoint follows it up, is held and then lowered when the room is predicted past the target, and rises again
    "rise and ease": [
        (18.0, None, 21.0, 21.0, None),
        (18.0, None, 21.0, 21.0, None),
        (18.3, 2.4, 21.0, 21.0, None),
        (18.9, 3.6, 21.0, 21.0, None),
        (19.5, 4.8, 21.0, 21.0, None),
        (20.1, 5.2, 21.0, 21.0, None),
        (20.7, 6.0, 21.0, 21.0, None),
        (21.0, 6.0, 21.0, 21.0, None),
        (21.2, 3.6, 21.0, 21.0, None),
        (21.3, 1.2, 21.0, 21.0, None),
        (21.1, -1.2, 21.0, 21.0, None),
        (20.8, -2.4, 21.0, 21.0, None),
    ],
    # The self-regulation asks for more than the target, then less, and the device is changed by the user once
    "self-regulation": [
        (18.0, None, 22.0, 21.0, None),
        (18.0, None, 22.5, 21.0, None),
        (18.5, 3.0, 22.5, 21.0, None),
        (19.1, 4.8, 22.5, 21.0, None),
        (19.9, 6.0, 22.5, 21.0, None),
        (20.6, 8.4, 22.0, 21.0, None),
        (21.0, 6.0, 21.5, 21.0, None),
        (21.3, 3.0, 20.5, 21.0, None),
        (21.2, 0.0, 22.0, 21.0, TRACKING),
        (21.2, 0.0, 22.0, 21.0, None),
        (21.2, 0.0, 22.0, 21.0, None),
        (21.0, -1.0, 22.0, 21.0, None),
    ],
    # The target is raised and lowered
    "target changes": [
        (18.0, None, 19.0, 19.0, None),
        (18.0, None, 19.0, 19.0, None),
        (18.5, 3.0, 19.0, 19.0, None),
        (18.8, 1.0, 23.0, 23.0, None),
        (19.2, 2.0, 23.0, 23.0, None),
        (19.9, 6.0, 23.0, 23.0, None),
        (20.6, 7.0, 20.0, 20.0, None),
        (20.6, 0.0, 20.0, 20.0, None),
    ],
}
SETTINGS = [
    # offset, max step, regulation step
    (-0.5, 1.0, 0.5),
    (1.0, 0.5, 0.5),
    (-1.0, 0.0, 0.5),
    (0.0, 1.0, 0.1),
]


def mirrored(value: float | None) -> float | None:
    """The value on the other side of the mirror axis."""
    return None if value is None else round(MIRROR - value, 4)


def run_scenario(rows, mode: str, offset: float, max_step: float, step: float) -> tuple[list[float], list[str | None], list[float]]:
    """Run the rows, one per cycle. In cool mode the rows are given inverted. Returns what is sent, the actions and the regulated temperatures."""
    ramp = SetpointRamp()
    clock = Clock()
    sent, actions, regulated = [], [], []
    for index, (room, slope, desired, target, cause) in enumerate(rows):
        if mode == "cool":
            room, slope, desired, target = mirrored(room), None if slope is None else -slope, mirrored(desired), mirrored(target)
        now = clock.now if index == 0 else clock.next_cycle()
        sent.append(adjust(ramp, now, desired, mode=mode, room=room, offset=offset, max_step=max_step, step=step, cause=cause, slope=slope, target=target))
        actions.append(ramp.action)
        regulated.append(desired)
    return sent, actions, regulated


@pytest.mark.parametrize("offset, max_step, step", SETTINGS)
@pytest.mark.parametrize("scenario", HEATING_SCENARIOS)
def test_cooling_is_the_exact_mirror_of_heating(scenario, offset, max_step, step) -> None:
    """With everything inverted, cooling sends the inverted setpoints and takes the same decisions as heating."""
    heat_sent, heat_actions, _ = run_scenario(HEATING_SCENARIOS[scenario], "heat", offset, max_step, step)
    cool_sent, cool_actions, _ = run_scenario(HEATING_SCENARIOS[scenario], "cool", offset, max_step, step)
    assert [mirrored(value) for value in cool_sent] == pytest.approx(heat_sent)
    assert cool_actions == heat_actions


@pytest.mark.parametrize("offset, max_step, step", SETTINGS)
@pytest.mark.parametrize("scenario", HEATING_SCENARIOS)
def test_the_setpoint_never_asks_for_more_than_the_regulated_temperature(scenario, offset, max_step, step) -> None:
    """Heating never sends more than the regulated temperature, and cooling never sends less: the ramp only makes the demand gentler."""
    heat_sent, _, heat_regulated = run_scenario(HEATING_SCENARIOS[scenario], "heat", offset, max_step, step)
    cool_sent, _, cool_regulated = run_scenario(HEATING_SCENARIOS[scenario], "cool", offset, max_step, step)
    assert all(sent <= regulated + 1e-9 for sent, regulated in zip(heat_sent, heat_regulated))
    assert all(sent >= regulated - 1e-9 for sent, regulated in zip(cool_sent, cool_regulated))


def test_the_mirror_scenarios_take_every_decision() -> None:
    """The scenarios are not trivial: between them they start, rise, reach, hold, lower, and follow the regulated temperature down."""
    seen = set()
    for rows in HEATING_SCENARIOS.values():
        seen.update(run_scenario(rows, "heat", -0.5, 1.0, 0.5)[1])
    # A change made on the device has no action
    assert seen - {None} == {ACTION_START, ACTION_UP, ACTION_REACHED, ACTION_HOLD, ACTION_DOWN}


def test_cooling_starts_gently_above_the_room() -> None:
    """A negative start offset is the gentle one in both modes: the unit starts with a setpoint which asks for nothing."""
    assert adjust(SetpointRamp(), START, 21, mode="heat", room=18.0, offset=-0.5) == 17.5
    assert adjust(SetpointRamp(), START, 23, mode="cool", room=26.0, offset=-0.5) == 26.5
    # A positive offset is the strong one in both modes
    assert adjust(SetpointRamp(), START, 21, mode="heat", room=18.0, offset=1.0) == 19.0
    assert adjust(SetpointRamp(), START, 23, mode="cool", room=26.0, offset=1.0) == 25.0


def test_a_warming_room_is_no_reason_to_ease_cooling() -> None:
    """The slope has a sign: a room which warms up in cool mode moves away from the target, and only a room which cools moves past it."""
    clock = Clock()
    ramp = started(clock, 23.0, cycles=4, mode="cool", room=26.0)
    assert ramp.value == 23
    # Warming at 12 degrees per hour: 23 + 1 is above the target, nothing to ease
    assert adjust(ramp, clock.next_cycle(), 23, mode="cool", room=23.0, slope=12.0) == 23
    assert ramp.action == ACTION_REACHED
    # Cooling at 12 degrees per hour: 23 - 1 is a degree past the target
    assert adjust(ramp, clock.next_cycle(), 23, mode="cool", room=23.0, slope=-12.0) == 23.5
    assert ramp.action == ACTION_DOWN


def test_a_cooling_room_is_no_reason_to_ease_heating() -> None:
    """The mirror: a room which cools down in heat mode is not predicted past the target."""
    clock = Clock()
    ramp = started(clock, cycles=4)
    assert ramp.value == 21
    assert adjust(ramp, clock.next_cycle(), 21, room=21.0, slope=-12.0) == 21
    assert ramp.action == ACTION_REACHED
