-- Runs only on a fresh local Docker volume. Never touches organizer data.
-- Defaults match .env.example: user alfa_events / password local_events_only.
-- If you change ALFA_EVENTS_USER / ALFA_EVENTS_PASSWORD, change them here too.

CREATE ROLE alfa_events LOGIN PASSWORD 'local_events_only';

CREATE DATABASE alfa_events OWNER alfa_events;
CREATE DATABASE alfa_events_test OWNER alfa_events;
