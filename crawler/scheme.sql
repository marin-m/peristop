CREATE DATABASE periscope
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_general_ci;

USE periscope;

CREATE TABLE peri (
    id VARCHAR(15) PRIMARY KEY NOT NULL,
    title VARCHAR(256) NOT NULL,
    country VARCHAR(2),
    lang VARCHAR(2),
    username VARCHAR(30) NOT NULL,
    running BOOLEAN NOT NULL,
    startDate DATETIME NOT NULL,
    endDate DATETIME,
    maxViewers INTEGER NOT NULL,
    totalViewers INTEGER,
    city VARCHAR(256),
    latitude DOUBLE,
    longitude DOUBLE,
    filter BOOLEAN
);

-- Chat and viewer info are stored to the disk.

