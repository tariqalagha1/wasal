-- QMS V1 canonical schema (MySQL 8)
-- Migration 0001 — initial domain schema

CREATE TABLE IF NOT EXISTS schema_migrations (
  version VARCHAR(255) PRIMARY KEY,
  applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);

CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('RECEPTIONIST','CASHIER','ADMIN') NOT NULL,
  preferred_locale ENUM('en','ar') NOT NULL DEFAULT 'en',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);

CREATE TABLE cashiers (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(30) NOT NULL UNIQUE,
  display_name VARCHAR(100) NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  sort_order INT NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);

CREATE TABLE guardians (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  external_guardian_id VARCHAR(100) NULL,
  name VARCHAR(200) NOT NULL,
  phone VARCHAR(50) NULL,
  UNIQUE KEY uq_guardian_external (external_guardian_id)
);

CREATE TABLE students (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  external_student_id VARCHAR(100) NULL,
  guardian_id BIGINT NOT NULL,
  name VARCHAR(200) NOT NULL,
  UNIQUE KEY uq_student_external (external_student_id),
  FOREIGN KEY (guardian_id) REFERENCES guardians(id)
);

CREATE TABLE appointments (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  source_system VARCHAR(60) NOT NULL,
  external_appointment_id VARCHAR(120) NOT NULL,
  booking_number VARCHAR(100) NOT NULL,
  guardian_id BIGINT NOT NULL,
  student_id BIGINT NULL,
  scheduled_at DATETIME(6) NOT NULL,
  status ENUM('SCHEDULED','CHECKED_IN','SERVED','MISSED','CANCELLED') NOT NULL DEFAULT 'SCHEDULED',
  imported_at DATETIME(6) NOT NULL,
  source_updated_at DATETIME(6) NULL,
  source_payload JSON NULL,
  UNIQUE KEY uq_appointment_source (source_system, external_appointment_id),
  KEY ix_appointments_day_booking (scheduled_at, booking_number),
  FOREIGN KEY (guardian_id) REFERENCES guardians(id),
  FOREIGN KEY (student_id) REFERENCES students(id)
);

CREATE TABLE visits (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  service_date DATE NOT NULL,
  guardian_id BIGINT NOT NULL,
  visit_type ENUM('SCHEDULED','EARLY','LATE','WALK_IN') NOT NULL,
  multi_appointment BOOLEAN NOT NULL DEFAULT FALSE,
  arrival_at DATETIME(6) NOT NULL,
  queue_entered_at DATETIME(6) NOT NULL,
  created_by BIGINT NOT NULL,
  notes VARCHAR(500) NULL,
  FOREIGN KEY (guardian_id) REFERENCES guardians(id),
  FOREIGN KEY (created_by) REFERENCES users(id),
  KEY ix_visits_day_guardian (service_date, guardian_id)
);

CREATE TABLE visit_appointments (
  visit_id BIGINT NOT NULL,
  appointment_id BIGINT NOT NULL,
  PRIMARY KEY (visit_id, appointment_id),
  UNIQUE KEY uq_active_appointment_visit (appointment_id),
  FOREIGN KEY (visit_id) REFERENCES visits(id),
  FOREIGN KEY (appointment_id) REFERENCES appointments(id)
);

CREATE TABLE daily_counters (
  service_date DATE PRIMARY KEY,
  last_ticket_number INT NOT NULL
);

CREATE TABLE queue_tickets (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  visit_id BIGINT NOT NULL UNIQUE,
  service_date DATE NOT NULL,
  ticket_number INT NOT NULL,
  status ENUM('WAITING','CALLED','SERVING','NO_SHOW','DONE','CANCELLED') NOT NULL,
  cashier_id BIGINT NULL,
  called_at DATETIME(6) NULL,
  service_started_at DATETIME(6) NULL,
  completed_at DATETIME(6) NULL,
  recall_count INT NOT NULL DEFAULT 0,
  cancellation_reason VARCHAR(300) NULL,
  version INT NOT NULL DEFAULT 1,
  UNIQUE KEY uq_daily_ticket (service_date, ticket_number),
  KEY ix_queue_next (service_date, status, ticket_number),
  KEY ix_queue_cashier_status (cashier_id, status),
  FOREIGN KEY (visit_id) REFERENCES visits(id),
  FOREIGN KEY (cashier_id) REFERENCES cashiers(id)
);

CREATE TABLE idempotency_keys (
  idempotency_key VARCHAR(100) PRIMARY KEY,
  operation VARCHAR(60) NOT NULL,
  response_code INT NOT NULL,
  response_body JSON NOT NULL,
  created_at DATETIME(6) NOT NULL
);

CREATE TABLE audit_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  occurred_at DATETIME(6) NOT NULL,
  actor_user_id BIGINT NULL,
  action VARCHAR(80) NOT NULL,
  entity_type VARCHAR(60) NOT NULL,
  entity_id BIGINT NOT NULL,
  from_state VARCHAR(30) NULL,
  to_state VARCHAR(30) NULL,
  details JSON NULL,
  correlation_id VARCHAR(100) NOT NULL,
  KEY ix_audit_entity (entity_type, entity_id, occurred_at),
  KEY ix_audit_correlation (correlation_id),
  FOREIGN KEY (actor_user_id) REFERENCES users(id)
);

CREATE TABLE import_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  service_date DATE NOT NULL,
  source_system VARCHAR(60) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  completed_at DATETIME(6) NULL,
  status ENUM('RUNNING','SUCCEEDED','FAILED','PARTIAL') NOT NULL,
  read_count INT NOT NULL DEFAULT 0,
  inserted_count INT NOT NULL DEFAULT 0,
  updated_count INT NOT NULL DEFAULT 0,
  rejected_count INT NOT NULL DEFAULT 0,
  error_summary TEXT NULL
);

CREATE TABLE system_settings (
  setting_key VARCHAR(100) PRIMARY KEY,
  setting_value JSON NOT NULL,
  updated_at DATETIME(6) NOT NULL,
  updated_by BIGINT NULL,
  FOREIGN KEY (updated_by) REFERENCES users(id)
);
