# Issue #1494 — pola parsowane, ale nieprzekazywane dalej (wszyscy providerzy)

Audyt wszystkich providerów z workoutami w tym repo: porównanie pól zadeklarowanych w surowym
schemacie Pydantic (`backend/app/schemas/providers/<provider>/*.py`) z tym, co faktycznie jest
czytane w `_normalize_workout` (`backend/app/services/providers/<provider>/workouts.py`).
Zakres: dane **workout/activity**.

| Grupa | Provider | Pole | Typ | Znaczenie | Lokalizacja (deklaracja) | Uwaga |
|---|---|---|---|---|---|---|
| A — manual/auto | Oura | `source` | enum: manual/autodetected/confirmed/workout_heart_rate | pochodzenie/wiarygodność treningu | `schemas/providers/oura/imports.py:30` | nieużywane w `oura/workouts.py` |
| A — manual/auto | Strava | `manual` | `bool \| None` | czy dodany ręcznie | `schemas/providers/strava/activity_import.py:67` | nieużywane w `strava/workouts.py` |
| A — manual/auto | Garmin | `manual` | `bool \| None` | czy dodany ręcznie | `schemas/providers/garmin/activity_import.py:38` | nieużywane w `garmin/workouts.py` |
| A — manual/auto | Garmin | `isWebUpload` | `bool \| None` | czy wgrany przez przeglądarkę (nie sync z urządzenia) | `schemas/providers/garmin/activity_import.py:37` | nieużywane w `garmin/workouts.py` |
| B — nazwa/notatka | Oura | `label` | `str \| None` | notatka/nazwa nadana przez użytkownika | `schemas/providers/oura/imports.py:29` | nieużywane w `oura/workouts.py`; pasuje do martwego `Workout.name` w API response |
| B — nazwa/notatka | Strava | `name` | `str` (wymagane!) | nazwa treningu | `schemas/providers/strava/activity_import.py:26` | nieużywane w `strava/workouts.py` |
| B — nazwa/notatka | Garmin | `activityName` | `str \| None` | nazwa treningu | `schemas/providers/garmin/activity_import.py:31` | nieużywane w `garmin/workouts.py` |
| B — nazwa/notatka | Suunto | `workoutName` (alias `name`) | `str \| None` | nazwa treningu | `schemas/providers/suunto/workout_import.py:147` | nieużywane w `suunto/workouts.py` |
| C — subiektywna intensywność | Oura | `intensity` | enum: easy/moderate/hard | subiektywna intensywność treningu | `schemas/providers/oura/imports.py:28` | nieużywane w `oura/workouts.py` |
| C — subiektywna intensywność | Polar | `training_load_pro.user_rpe` | `str \| None` | self-reported Rate of Perceived Exertion | `schemas/providers/polar/exercise_import.py:38` | nieużywane w `polar/workouts.py` |
| C — subiektywna intensywność | Whoop | `score.strain` | `float \| None` (0-21) | wyliczona intensywność treningu | `schemas/providers/whoop/workout_import.py:7` | **już obsłużone** — `HealthScoreCreate(category=STRAIN)`, `whoop/workouts.py:240-279`; wzorzec do skopiowania dla Oura/Polar |
| Unikalne | Strava | `trainer` | `bool \| None` | trening stacjonarny (trenażer) | `activity_import.py:65` | brak odpowiednika |
| Unikalne | Strava | `commute` | `bool \| None` | czy dojazd do pracy | `activity_import.py:66` | brak odpowiednika |
| Unikalne | Strava | `private` | `bool \| None` | czy trening prywatny | `activity_import.py:68` | brak odpowiednika |
| Unikalne | Strava | `gear` / `gear_id` | obiekt / `str` | sprzęt użyty (buty/rower) | `activity_import.py:62-63` | inny "gear" niż Suunto (sprzęt sportowy, nie urządzenie rejestrujące) |
| Unikalne | Strava | `device_watts` | `bool \| None` | czy moc z realnego miernika, czy estymowana | `activity_import.py:52` | brak odpowiednika |
| Unikalne | Strava | `has_heartrate` | `bool \| None` | czy trening ma dane HR | `activity_import.py:42` | brak odpowiednika |
| Unikalne | Strava | `weighted_average_watts` | `int \| None` | ważona średnia moc | `activity_import.py:51` | brak odpowiednika |
| Unikalne | Polar | `training_load` | `float \| None` | ogólne obciążenie treningowe | `exercise_import.py:60` | brak odpowiednika |
| Unikalne | Polar | `training_load_pro.cardio_load/muscle_load/perceived_load` (+interpretacje) | `float \| None` / `str \| None` | rozbicie obciążenia treningowego | `exercise_import.py:30-37` | brak odpowiednika |
| Unikalne | Polar | `has_route` / `route` | `bool` / lista pkt GPS | ślad GPS treningu | `exercise_import.py:62,73` | brak odpowiednika |
| Unikalne | Polar | `heart_rate_zones` | lista stref HR | czas w strefach tętna | `exercise_import.py:58` | brak odpowiednika (Whoop ma to obsłużone jako `hr_zones` JSONB — mógłby być wzorcem) |
| Unikalne | Polar | `fat/carbohydrate/protein_percentage` | `int \| None` | źródła energii spalanej | `exercise_import.py:64-66` | brak odpowiednika |
| Unikalne | Polar | `running_index` | `int \| None` | wskaźnik wydolności biegowej | `exercise_import.py:67` | brak odpowiednika |
| Unikalne | Polar | `club_id` / `club_name` | `int \| None` / `str \| None` | klub sportowy | `exercise_import.py:69-70` | brak odpowiednika |
| Unikalne | Suunto | `notes` | `str \| None` | wolna notatka (odrębna od nazwy) | `workout_import.py:148` | brak odpowiednika |
| Bug wiring (nie luka schematu) | Suunto | `avgCadence` / `maxCadence` | `float \| None` | kadencja | `workout_import.py:137-138` | pole docelowe `EventRecordMetrics.average_cadence` **już istnieje**, po prostu nieużywane |
| Bug wiring (nie luka schematu) | Garmin | `averageSpeedInMetersPerSecond` | `float \| None` | prędkość średnia | `activity_import.py:33` | pole docelowe `EventRecordMetrics.average_speed` **już istnieje**, po prostu nieużywane |

## Istniejące, działające wzorce (precedensy do skopiowania)

| Wzorzec | Provider | Gdzie |
|---|---|---|
| Mapowanie na istniejące, generyczne pole `EventRecordCreate` | Suunto `gear` → `device_model`/`software_version` | `suunto/workouts.py:169-186,250-257,301-309` |
| JSONB "kubełek" na strukturalne dane provider-specific | Whoop `hr_zones`/`power_zones`/`segments` → `WorkoutDetails` (kolumny `json_binary`, GIN index) | `models/workout_details.py`, `whoop/workouts.py:192,317` |
| Dedykowany model na skalarną wartość intensywności/jakości | Whoop `score.strain` → `HealthScoreCreate(category=STRAIN)` | `whoop/workouts.py:240-279` |

## Poza zakresem

Fitbit (surowy `dict[str, Any]`, brak modelu Pydantic), Samsung, Apple, Google, Sensorbio, Ultrahuman —
brak dedykowanego schematu workout JSON / brak `workouts.py` dla workoutów w tym repo.
