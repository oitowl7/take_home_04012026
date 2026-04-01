ALTER SESSION SET TIMEZONE = 'UTC';
-- =========================
-- Dimension Tables
-- =========================

CREATE OR REPLACE TABLE users (
  user_id         STRING          NOT NULL,
  is_registered   BOOLEAN,
  CONSTRAINT pk_users PRIMARY KEY (user_id)
);
CREATE OR REPLACE TABLE hotels (
  hotel_id        STRING          NOT NULL,
  location        STRING,
  total_rooms     NUMBER,
  CONSTRAINT pk_hotels PRIMARY KEY (hotel_id)
);
CREATE OR REPLACE TABLE flights (
  flight_id             STRING        NOT NULL,
  departure_airport     STRING,
  arrival_airport       STRING,
  departure_time        TIMESTAMP_TZ,
  arrival_time          TIMESTAMP_TZ,
  passenger_capacity    NUMBER,
  CONSTRAINT pk_flights PRIMARY KEY (flight_id)
);
CREATE OR REPLACE TABLE cars (
  car_id               STRING         NOT NULL,
  model                STRING,
  passenger_capacity   NUMBER,
  CONSTRAINT pk_cars PRIMARY KEY (car_id)
);
-- "date" is a reserved word; quote it if you want exact table name.
CREATE OR REPLACE TABLE "date" (
  date_id          STRING      NOT NULL,
  year             NUMBER,
  quarter          NUMBER,
  month            NUMBER,
  day              NUMBER,
  CONSTRAINT pk_date PRIMARY KEY (date_id)
);
-- =========================
-- Fact Tables
-- =========================
CREATE OR REPLACE TABLE searches (
  search_id         STRING          NOT NULL,
  user_id           STRING          COMMENT 'FK (not enforced): users.user_id',
  date_id           STRING          COMMENT 'FK (not enforced): "date".date_id',
  search_type       STRING,
  "timestamp"       TIMESTAMP_TZ,
  CONSTRAINT pk_searches PRIMARY KEY (search_id)
);
CREATE OR REPLACE TABLE flight_search (
  search_id             STRING        NOT NULL COMMENT 'PK; FK (not enforced): searches.search_id',
  departure_airport     STRING,
  arrival_airport       STRING,
  arrival_time          TIMESTAMP_TZ,
  departure_time        TIMESTAMP_TZ,
  passenger_capacity    NUMBER,
  CONSTRAINT pk_flight_search PRIMARY KEY (search_id)
);
CREATE OR REPLACE TABLE hotel_search (
  search_id           STRING         NOT NULL COMMENT 'PK; FK (not enforced): searches.search_id',
  location            STRING,
  rooms_requested     NUMBER,
  CONSTRAINT pk_hotel_search PRIMARY KEY (search_id)
);
CREATE OR REPLACE TABLE car_search (
  search_id             STRING       NOT NULL COMMENT 'PK; FK (not enforced): searches.search_id',
  model                 STRING,
  passenger_capacity    NUMBER,
  CONSTRAINT pk_car_search PRIMARY KEY (search_id)
);
CREATE OR REPLACE TABLE bookings (
  booking_sk        STRING          NOT NULL COMMENT 'Surrogate version key (PK)',
  booking_id        STRING          NOT NULL COMMENT 'Business booking id (can repeat across versions)',
  user_id           STRING          COMMENT 'FK (not enforced): users.user_id; indexed in source model',
  date_id           STRING          COMMENT 'FK (not enforced): "date".date_id; indexed in source model',
  amount_total      NUMBER(18,2),
  valid_from        TIMESTAMP_TZ,
  valid_to          TIMESTAMP_TZ,
  is_current        BOOLEAN,
  status            STRING,
  CONSTRAINT pk_bookings PRIMARY KEY (booking_sk),
  CONSTRAINT uq_bookings_business_version UNIQUE (booking_id, valid_from)
);
CREATE OR REPLACE TABLE booking_items (
  booking_item_id   STRING          NOT NULL,
  booking_sk        STRING          NOT NULL COMMENT 'FK (not enforced): bookings.booking_sk; one row per booking version',
  booking_id        STRING          COMMENT 'Business booking id (optional copy for convenience)',
  booking_type      STRING          COMMENT 'Indexed in source model',
  flight_id         STRING          COMMENT 'FK (not enforced): flights.flight_id',
  hotel_id          STRING          COMMENT 'FK (not enforced): hotels.hotel_id',
  car_id            STRING          COMMENT 'FK (not enforced): cars.car_id',
  CONSTRAINT pk_booking_items PRIMARY KEY (booking_item_id),
  CONSTRAINT uq_booking_items_booking_sk UNIQUE (booking_sk),
  CONSTRAINT chk_booking_items_type_and_id CHECK (
    (booking_type = 'FLIGHT' AND flight_id IS NOT NULL AND hotel_id IS NULL AND car_id IS NULL) OR
    (booking_type = 'HOTEL'  AND hotel_id IS NOT NULL AND flight_id IS NULL AND car_id IS NULL) OR
    (booking_type = 'CAR'    AND car_id IS NOT NULL AND flight_id IS NULL AND hotel_id IS NULL)
  )
);
