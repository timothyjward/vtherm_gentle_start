"""Pure business logic of the setpoint ramp.

This module is free of any Home Assistant dependency so that it can be unit
tested in isolation. It keeps the ramp position and decides, each time the
thermostat computes its regulated temperature, which setpoint is sent.

The ramp only ever moves between two bounds set by the thermostat: it never
goes above the regulated temperature computed by Versatile Thermostat, and a
lower regulated temperature is applied at once. It limits how fast the setpoint
approaches the regulated temperature, it does not compete with it.
"""

from __future__ import annotations

from datetime import datetime

from .const import (
    COMMAND_CAUSE_UNDERLYING_TRACKING,
    CYCLE_TOLERANCE_SEC,
    SLOPE_WARMUP_CYCLES,
    VTHERM_HVAC_MODE_COOL,
    VTHERM_HVAC_MODE_HEAT,
)

#: What the ramp did at its last decision.
ACTION_START = "start"
ACTION_UP = "up"
ACTION_REACHED = "reached"
ACTION_HOLD = "hold"
ACTION_DOWN = "down"


def round_to_nearest(value: float, step: float) -> float:
    """Round a value to the nearest multiple of the step."""
    if not step:
        return value
    return round(round(value / step) * step, 10)


def effective_step(max_step: float, regulation_step: float) -> tuple[float, bool]:
    """Return the maximum change per cycle and whether it had to be raised.

    0 means no limit. The step is never lower than the rounding step of the
    thermostat, else the rounding would cancel each change and the ramp would
    never move.
    """
    if max_step <= 0:
        return 0.0, False
    if max_step < regulation_step:
        return regulation_step, True
    return max_step, False


class SetpointRamp:
    """The position of a setpoint ramp and the rules which move it."""

    def __init__(self) -> None:
        """Initialize a ramp which has not started."""
        self._value: float | None = None
        self._mode: str | None = None
        self._last_advance: datetime | None = None
        self._started_at: datetime | None = None
        self._restored_value: float | None = None
        self._action: str | None = None

    @property
    def value(self) -> float | None:
        """The setpoint the ramp currently sends, None when no ramp is in progress."""
        return self._value

    @property
    def action(self) -> str | None:
        """What the ramp did at its last decision, None when it has not decided yet."""
        return self._action

    def reset(self) -> None:
        """Forget the ramp position: the next regulation starts a new ramp."""
        self._value = None
        self._mode = None
        self._last_advance = None
        self._started_at = None
        self._action = None

    def restore(self, value: float) -> None:
        """Resume from this position the next time the ramp starts, after a restart."""
        self._restored_value = value

    def adjust(
        self,
        desired: float,
        regulation_step: float,
        command_cause: str | None,
        *,
        mode: str,
        current_temperature: float | None,
        now: datetime,
        cycle_seconds: float,
        start_offset: float,
        max_step: float,
        target: float | None = None,
        slope_per_hour: float | None = None,
        horizon_seconds: float | None = None,
    ) -> float:
        """Return the setpoint to send for the desired setpoint.

        The ramp starts at the room temperature plus the start offset when
        heating (minus it when cooling), never beyond the desired setpoint, then
        moves towards it by at most one step per cycle. A change which reduces
        the demand, such as a lower target, is applied at once.

        When the slope of the room temperature shows that it would pass the
        target before the next decision, the setpoint is not raised, and it is
        lowered if the room would pass the target by a whole regulation step.
        The desired setpoint stays the upper bound: the ramp never competes with it.
        """
        if command_cause == COMMAND_CAUSE_UNDERLYING_TRACKING:
            # The device was changed by the user and the thermostat follows it: do not override it
            self._start(desired, mode, now, None)
            return desired

        if self._mode is not None and self._mode != mode:
            # Heating becomes cooling or the other way round: the ramp has to start again
            self.reset()

        if self._value is None:
            if self._restored_value is not None:
                # Restart of Home Assistant while ramping: resume where the ramp was
                self._start(self._restored_value, mode, now, ACTION_START)
                self._restored_value = None
            elif current_temperature is None:
                # Without the room temperature there is nothing to start from
                return desired
            else:
                self._start(self._compute_start(desired, regulation_step, mode, current_temperature, start_offset), mode, now, ACTION_START)
                return self._value

        direction = -1 if mode == VTHERM_HVAC_MODE_COOL else 1
        followed = direction * (desired - self._value) < 0
        if followed:
            # The thermostat asks for less than the ramp: it is applied at once
            self._value = desired
            self._action = ACTION_DOWN
        if self._is_step_due(now, cycle_seconds):
            self._decide(
                desired,
                regulation_step,
                direction=direction,
                mode=mode,
                current_temperature=current_temperature,
                now=now,
                cycle_seconds=cycle_seconds,
                start_offset=start_offset,
                max_step=max_step,
                target=target,
                slope_per_hour=slope_per_hour,
                horizon_seconds=horizon_seconds,
            )
            if followed:
                # The setpoint was lowered to follow the thermostat: that is the news, whatever the decision after it was
                self._action = ACTION_DOWN
        return self._value

    def _start(self, value: float, mode: str, now: datetime, action: str | None) -> None:
        """Position the ramp. The next decision is due in a whole cycle, not at once."""
        self._value = value
        self._mode = mode
        self._last_advance = now
        self._started_at = now
        self._action = action

    def _decide(
        self,
        desired: float,
        regulation_step: float,
        *,
        direction: int,
        mode: str,
        current_temperature: float | None,
        now: datetime,
        cycle_seconds: float,
        start_offset: float,
        max_step: float,
        target: float | None,
        slope_per_hour: float | None,
        horizon_seconds: float | None,
    ) -> None:
        """Take the decision of one cycle: raise the setpoint, hold it or lower it."""
        if not self._is_warm(now, cycle_seconds):
            slope_per_hour = None
        horizon = horizon_seconds or cycle_seconds
        if self._last_advance is not None:
            # A decision can come later than planned (a missed tick, a regulation period which is not a whole number of cycles):
            # look as far ahead as the last wait, but not more than twice the planned time
            horizon = max(horizon, min((now - self._last_advance).total_seconds(), 2 * horizon))
        self._last_advance = now

        overshoot = self._predicted_overshoot(desired, direction, current_temperature, target, slope_per_hour, horizon)
        if overshoot > 0:
            if overshoot >= regulation_step:
                eased = self._ease(desired, regulation_step, direction, mode, current_temperature, start_offset, max_step)
                self._action = ACTION_DOWN if eased != self._value else ACTION_HOLD
                self._value = eased
            else:
                self._action = ACTION_HOLD
            return

        gap = direction * (desired - self._value)
        if gap > 0:
            step, _ = effective_step(max_step, regulation_step)
            self._value = round(self._value + direction * (gap if step <= 0 else min(gap, step)), 2)
            self._action = ACTION_UP
        else:
            self._action = ACTION_REACHED

    @staticmethod
    def _predicted_overshoot(
        desired: float,
        direction: int,
        current_temperature: float | None,
        target: float | None,
        slope_per_hour: float | None,
        horizon_seconds: float,
    ) -> float:
        """How far past the target the room is expected to be at the next decision, 0 when it is not expected to pass it.

        The target is the one of the thermostat: the desired setpoint can be above it when the self-regulation compensates for a device.
        """
        if current_temperature is None or slope_per_hour is None:
            return 0.0
        reference = desired if target is None else target
        predicted = current_temperature + slope_per_hour * horizon_seconds / 3600
        return max(0.0, round(direction * (predicted - reference), 3))

    def _ease(
        self,
        desired: float,
        regulation_step: float,
        direction: int,
        mode: str,
        current_temperature: float | None,
        start_offset: float,
        max_step: float,
    ) -> float:
        """Lower the demand by one step, not beyond the gentlest level, which is the start level without a positive offset."""
        step, _ = effective_step(max_step, regulation_step)
        increment = step if step > 0 else regulation_step
        lowest = self._compute_start(desired, regulation_step, mode, current_temperature, min(start_offset, 0.0))
        demand = direction * self._value
        return round(direction * max(demand - increment, min(demand, direction * lowest)), 2)

    @staticmethod
    def _compute_start(desired: float, regulation_step: float, mode: str, current_temperature: float, start_offset: float) -> float:
        """Compute the setpoint the ramp starts from, never beyond the desired setpoint."""
        if mode == VTHERM_HVAC_MODE_COOL:
            return max(desired, round_to_nearest(current_temperature - start_offset, regulation_step))
        return min(desired, round_to_nearest(current_temperature + start_offset, regulation_step))

    def _is_warm(self, now: datetime, cycle_seconds: float) -> bool:
        """True once the ramp has run long enough for the slope of the room temperature to describe the heating."""
        if self._started_at is None:
            return False
        return (now - self._started_at).total_seconds() >= SLOPE_WARMUP_CYCLES * cycle_seconds - CYCLE_TOLERANCE_SEC

    def _is_step_due(self, now: datetime, cycle_seconds: float) -> bool:
        """True if a whole cycle has elapsed since the ramp last decided."""
        if self._last_advance is None:
            return True
        return (now - self._last_advance).total_seconds() >= cycle_seconds - CYCLE_TOLERANCE_SEC


def is_ramp_mode(mode: str | None) -> bool:
    """True for the HVAC modes in which a setpoint ramp applies."""
    return mode in (VTHERM_HVAC_MODE_HEAT, VTHERM_HVAC_MODE_COOL)
