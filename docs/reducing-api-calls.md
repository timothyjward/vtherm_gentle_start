# Reducing API calls

Each step of the ramp is a command sent to the device. If the device is reached through a cloud service which limits the number of requests per minute or per day, the commands of a ramp count against that limit. This page shows how many commands a switch-on sends and how to send fewer.

## Commands per switch-on

A switch-on sends four fixed commands, and each following cycle which moves the setpoint sends one more until the target is reached:

1. the start setpoint, sent before the device is switched on;
2. the mode;
3. the setpoint again, which VTherm sends after the mode change;
4. the setpoint once more, about two seconds later, which VTherm repeats to make sure the device has it;
5. one command per step of the ramp.

Without the plugin a switch-on sends three commands: the mode, the setpoint and its repeat. The plugin adds the first command and the steps.

The number of steps is the distance from the start setpoint to the target divided by the maximum step, rounded up. A step of 0 removes the limit, so there is a single step.

These figures were measured on the call events of a local Home Assistant test instance with Versatile Thermostat `10.6.4`, a room at 18 degrees, a target of 21, the defaults and a cycle of one minute. The device received `17.5`, the mode, `17.5`, `17.5` two seconds later, then `18.5`, `19.5`, `20.5` and `21.0` at one minute intervals: 8 commands. Your device integration may send more calls of its own, for example a refresh after each command.

Example: the room is at 20 degrees and the target is 23 degrees, with a regulation step of 0.5.

| Start offset | Maximum step | Setpoints sent after the start | Steps | Commands |
| --- | --- | --- | --- | --- |
| -0.5 | 0.5 | 20, 20.5, 21 and so on up to 23 | 7 | 11 |
| -0.5 (default) | 1.0 (default) | 20.5, 21.5, 22.5, 23 | 4 | 8 |
| -0.5 | 2.0 | 21.5, 23 | 2 | 6 |
| -0.5 | 0 (no limit) | 23 | 1 | 5 |
| 0 | 1.0 | 21, 22, 23 | 3 | 7 |
| 0 | 2.0 | 22, 23 | 2 | 6 |
| 1.0 | 1.0 | 22, 23 | 2 | 6 |

The counts are exact for a constant target. They are lower when:

* the slope guard holds the setpoint (a hold sends nothing);
* a step is smaller than `auto_regulation_dtemp` of the thermostat, because VTherm does not send a change smaller than that.

They are higher when the setpoint is lowered by the slope guard, or when the target changes during the ramp.

## How to send fewer

1. **Increase the maximum step.** This is the most effective setting. Each step removed saves one command. A step of 2.0 halves the number of steps of the default, and the start is still gentle. The four fixed commands remain, so the floor with the plugin is 5.
2. **Use a less negative start offset, or none.** The ramp starts closer to the target and needs fewer steps.
3. **Raise `auto_regulation_dtemp` on the thermostat.** Small changes are not sent. Keep the maximum step at or above this value.
4. **Enable the plugin only on the thermostats which need it.** Each enabled thermostat adds commands at every start.
5. **Reduce the number of starts.** A wider hysteresis or a longer cycle, and less use of the auto start and stop feature of VTherm, mean fewer switch-ons, and each switch-on costs a ramp.
6. **Poll the device less often.** For many cloud integrations the polling interval is the largest fixed cost. Each poll is usually one request, whatever the number of units.
7. **Refresh only when you need it.** A refresh after each start does not help the ramp. If you press a refresh button from an automation, do it only after a thermostat stops, as in the next section.

A longer `auto_regulation_periode_min` or `cycle_min` spreads the same commands over more time. It does not reduce their number.

## Making sure a device switches off

A cloud call can fail. If the command which switches a device off fails, the device keeps running while the thermostat believes it is off, and the room can overheat or overcool. This is not specific to the plugin, but a service with a quota makes it more likely when the quota is exhausted.

The example automation below refreshes the device state 45 seconds after a thermostat stops, and, 45 seconds later, switches off any device which is still on. It costs a refresh only when a thermostat stops, and a command only when a device is still on.

```yaml
alias: Ensure A/C turns off
description: Refresh the device state after a thermostat stops, then switch off any unit still on
mode: parallel
max: 5
triggers:
  - trigger: state
    entity_id:
      - climate.thermostat_bedroom
      - climate.thermostat_office
    attribute: current_state
conditions:
  - condition: template
    value_template: >
      {{ states(trigger.entity_id) == 'off'
         or state_attr(trigger.entity_id, 'hvac_action') in ['off', 'idle'] }}
actions:
  - delay: "00:00:45"
  - action: button.press
    target:
      entity_id: button.air_conditioner_refresh
  - delay: "00:00:45"
  - variables:
      underlying: "{{ state_attr(trigger.entity_id, 'underlying_entities') or [] }}"
  - if:
      - condition: template
        value_template: >
          {{ underlying | length > 0
             and (states(trigger.entity_id) == 'off'
                  or state_attr(trigger.entity_id, 'hvac_action') in ['off', 'idle'])
             and not is_state(underlying[0], 'off') }}
    then:
      - action: climate.turn_off
        target:
          entity_id: "{{ underlying }}"
```

Notes on the example:

* Replace the thermostat entities and the refresh button with yours. The refresh button is the one of your device integration, if it has one.
* The state of a climate entity is its HVAC mode, so `idle` can only be tested on the `hvac_action` attribute, as the example does. Check in **Developer tools, States** what the `current_state` and `hvac_action` attributes of your thermostat hold before relying on the trigger.
* `mode: parallel` lets several thermostats stop within the delay. With `mode: single` a second thermostat which stops during the delay is ignored, and its device stays on.
* The example is not part of the plugin. Its logic was exercised against mock thermostats, with a mock refresh button and a mock `climate.turn_off`, not against a real device.
