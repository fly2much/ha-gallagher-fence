# Gallagher Fence (read-only) for Home Assistant

Reads Gallagher i Series electric fence energiser, zone and earth data from the Gallagher cloud (the same service the Gallagher Devices app uses) into Home Assistant.

**Read-only by design.**  This integration never turns an energiser on or off and never changes any Gallagher setting.  The Gallagher app stays in charge of the fence; Home Assistant only watches.

## What you get

- One device per energiser with fence voltage (kV), current (A), status, battery status and last-reading time
- Voltage and current for every zone monitor and the earth monitor
- Battery voltage, supply voltage and energiser temperature where the model reports them (e.g. MB2800i on an App Gateway)
- "Gateway connected" and "Readings out of date" binary sensors per energiser
- Active alert count for the farm

## Install (HACS)

1. HACS -> Integrations -> three dots -> **Custom repositories** -> add this repo URL, category **Integration**
2. Install **Gallagher Fence (read-only)** and restart Home Assistant
3. Settings -> Devices & services -> **Add integration** -> Gallagher Fence -> log in with your Gallagher account

## Settings

Devices & services -> Gallagher Fence -> **Configure**:

- Check every (minutes) - default 5.  Gateways report about every 30 minutes, so faster polling gains little.
- Flag readings as out of date after (hours) - default 3.

## Notes

- Uses an undocumented API.  Gallagher could change it at any time.
- Zone entries whose last reading is more than 30 days older than the rest of the energiser are treated as leftovers from replaced monitors and skipped.
