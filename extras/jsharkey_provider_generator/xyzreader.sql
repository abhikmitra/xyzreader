/*
{@name Items}
{@package com.example.xyzreader}
*/

/**
 * {@exportAs Items}
 * {@matchDir  /items/}
 * {@matchItem /items/[_id]/}
 */
CREATE TABLE items (
  _id INTEGER PRIMARY KEY AUTOINCREMENT,
  server_id TEXT,
  title TEXT NOT NULL,
  author TEXT NOT NULL,
  body TEXT NOT NULL,
  photo_url TEXT NOT NULL,
  published_date INTEGER NOT NULL DEFAULT 0
);
