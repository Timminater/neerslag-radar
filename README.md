# Neerslag Radar for Home Assistant

<p align="center">
  <img src="assets/logo.png" alt="Neerslag Radar logo" width="220">
</p>

[![HACS validation](https://github.com/Timminater/neerslag-radar/actions/workflows/validate.yml/badge.svg)](https://github.com/Timminater/neerslag-radar/actions/workflows/validate.yml)
[![Tests](https://github.com/Timminater/neerslag-radar/actions/workflows/tests.yml/badge.svg)](https://github.com/Timminater/neerslag-radar/actions/workflows/tests.yml)

Neerslag Radar is a HACS custom integration for short-term precipitation
forecasts from Buienradar, Buienalarm, KNMI and Open-Meteo. Each configured location
can have one subentry per provider, so a failing provider does not replace or combine
data from another source.

> [!IMPORTANT]
> This integration is experimental. Buienalarm uses an undocumented endpoint and the
> KNMI seamless ensemble product is experimental. Either source can change or disappear
> without notice.
>
> KNMI files are read with a pure-Python HDF5 reader, so Home Assistant does not need to
> compile optional NetCDF or projection libraries.

## Requirements

- Home Assistant 2026.6.0 or newer
- HACS for the recommended installation method
- A registered KNMI Open Data API key is recommended when using KNMI. A shared anonymous
  test key can be selected during setup, but its shared quota makes it unsuitable for
  reliable day-to-day use.

## Installation

1. Open HACS in Home Assistant.
2. Add `https://github.com/Timminater/neerslag-radar` as a custom repository
   with category **Integration**.
3. Install **Neerslag Radar** and restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**.
5. Search for **Neerslag Radar**, create a location and add providers.

Manual installation is also possible by copying
`custom_components/neerslag_radar` to the `custom_components` directory in
your Home Assistant configuration directory, followed by a restart.

## Providers

| Provider | Resolution | Available horizon | Default poll | Notes |
|---|---:|---:|---:|---|
| Buienradar | 5 minutes | About 2 hours | 5 minutes | Public `raintext` feed |
| Buienalarm | Usually 5 minutes | About 2 hours | 5 minutes | Undocumented and experimental |
| KNMI | 5 minutes | First 3 hours exposed | 10 minutes | 20-member ensemble; registered key recommended |
| Open-Meteo | 15 minutes | 3 hours | 15 minutes | Free for non-commercial home automation |

Poll intervals can be changed through provider reconfiguration, but only within safe
limits: 5–15 minutes for Buienradar and Buienalarm, 5–30 for KNMI and 15–60 for
Open-Meteo.

Create a registered KNMI key on the
[Open Data API token page](https://developer.dataplatform.knmi.nl/open-data-api#token).
For testing, setup can use KNMI's built-in anonymous key. It is shared by all anonymous
users, is limited to 50 requests per minute and 3,000 requests per hour in total, and
can be unavailable when that shared quota is exhausted. The currently included key
expires on 1 August 2027.
The integration uses the
[seamless ensemble precipitation forecast](https://dataplatform.knmi.nl/en/dataset/seamless-precipitation-ensemble-forecast-members-1-0),
downloads each new file once, samples only the configured 1×1-km cells and deletes the
temporary file when it is replaced or the integration unloads.

## Entities

Every provider creates one device containing:

- **Forecast total**: total expected precipitation over the provider's available
  horizon. Its `forecast` attribute contains every normalized point.
- **Forecast slot 1…N**: stable relative slots. The state is expected precipitation
  in millimetres for that interval.

Slot attributes include:

- `datetime`: exact UTC forecast timestamp
- `interval_minutes`: interval length
- `precipitation`: millimetres in the interval
- `precipitation_intensity`: equivalent `mm/h`
- `probability` and `uncertainty`: available for KNMI ensemble points
- `provider` and `slot`

The integration also creates a **Global** device whenever at least one provider is
configured. It exposes 36 five-minute slots and a total sensor. Provider amounts are
first distributed proportionally over matching five-minute intervals; each Global slot
then uses the highest available provider amount. Its attributes include
`selected_provider` and `provider_values`, so the chosen source remains transparent.

A Global slot stays available while at least one provider has a current forecast. The
Global total is a conservative maximum envelope and can therefore combine different
providers across its three-hour horizon.

Providers are never blended and missing horizons are never extrapolated. A provider
update failure marks only that provider's entities unavailable; the coordinator keeps
the last valid response internally and publishes new data after recovery.

## Lovelace card compatibility

Version 0.3.0 and newer is compatible with
[Timminater/neerslag-radar-card](https://github.com/Timminater/neerslag-radar-card).
The card automatically finds provider forecast-total sensors for configured locations;
the calculated **Global** sensor is deliberately excluded. Each recognised sensor
exposes a stable location identifier, location name and forecast schema version in its
attributes.

## Example automation

Use a native numeric-state trigger on an upcoming slot:

```yaml
triggers:
  - trigger: numeric_state
    entity_id: sensor.home_buienradar_forecast_slot_1
    above: 0.2
actions:
  - action: notify.notify
    data:
      message: "Rain is expected in the next interval."
```

Entity IDs depend on the location and provider names generated by Home Assistant.

## Data use and attribution

- Buienradar data: [buienradar.nl](https://www.buienradar.nl/)
- Buienalarm data: [buienalarm.nl](https://www.buienalarm.nl/)
- KNMI data: [KNMI Data Platform](https://dataplatform.knmi.nl/), CC BY 4.0
- Open-Meteo data: [Open-Meteo](https://open-meteo.com/), CC BY 4.0. The free API is
  limited to non-commercial use under its [terms](https://open-meteo.com/en/terms).

## Troubleshooting

- Download diagnostics from the integration entry. API keys and coordinates are
  redacted.
- A KNMI `invalid_auth` error means the registered or shared key was rejected. Replace
  the registered key, or check the anonymous key and expiry information on the
  [KNMI token page](https://developer.dataplatform.knmi.nl/open-data-api#token).
- Buienalarm may return HTML, 5xx responses or a changed schema. The integration fails
  closed instead of reporting false dry weather.
- Enable debug logging for `custom_components.neerslag_radar` when reporting an
  issue, but never publish an unredacted API key.

Please report bugs through the [issue tracker](https://github.com/Timminater/neerslag-radar/issues).
