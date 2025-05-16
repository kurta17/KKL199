/*
This file describes the database schema for the ChainChess application.
Execute these SQL statements in your Supabase SQL editor to set up the required tables.
*/

-- Users table
CREATE TABLE users (
  id UUID PRIMARY KEY REFERENCES auth.users(id),
  username TEXT UNIQUE NOT NULL,
  email TEXT UNIQUE NOT NULL,
  public_key TEXT NOT NULL,
  rating INTEGER DEFAULT 1200,
  wins INTEGER DEFAULT 0,
  losses INTEGER DEFAULT 0,
  draws INTEGER DEFAULT 0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create a trigger to update the updated_at field
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_timestamp
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE PROCEDURE update_timestamp();

-- Games table
CREATE TABLE games (
  id UUID PRIMARY KEY,
  white_player_id UUID NOT NULL REFERENCES users(id),
  black_player_id UUID NOT NULL REFERENCES users(id),
  status TEXT NOT NULL CHECK (status IN ('pending', 'active', 'completed', 'abandoned')),
  result JSONB,
  draw_offered_by UUID REFERENCES users(id),
  draw_offered_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE
);

-- Moves table
CREATE TABLE moves (
  id SERIAL PRIMARY KEY,
  game_id UUID NOT NULL REFERENCES games(id),
  move_number INTEGER NOT NULL,
  color TEXT NOT NULL CHECK (color IN ('white', 'black')),
  from_square TEXT NOT NULL,
  to_square TEXT NOT NULL,
  fen_after TEXT NOT NULL,
  signature TEXT NOT NULL,
  player_id UUID NOT NULL REFERENCES users(id),
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on game_id and move_number for fast lookups
CREATE INDEX idx_moves_game_move ON moves (game_id, move_number);

-- Game verification table for storing Merkle roots
CREATE TABLE game_verifications (
  id SERIAL PRIMARY KEY,
  game_id UUID NOT NULL REFERENCES games(id) UNIQUE,
  merkle_root TEXT NOT NULL,
  verified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Row level security policies
-- Enable RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE games ENABLE ROW LEVEL SECURITY;
ALTER TABLE moves ENABLE ROW LEVEL SECURITY;
ALTER TABLE game_verifications ENABLE ROW LEVEL SECURITY;

-- Users policies
CREATE POLICY "Users can view any user profile" 
ON users FOR SELECT 
USING (true);

CREATE POLICY "Users can update own profile" 
ON users FOR UPDATE 
USING (auth.uid() = id);

-- Games policies
CREATE POLICY "Users can view their games" 
ON games FOR SELECT 
USING (auth.uid() = white_player_id OR auth.uid() = black_player_id);

CREATE POLICY "Users can create games" 
ON games FOR INSERT 
WITH CHECK (auth.uid() = white_player_id OR auth.uid() = black_player_id);

CREATE POLICY "Players can update their games" 
ON games FOR UPDATE 
USING (auth.uid() = white_player_id OR auth.uid() = black_player_id);

-- Moves policies
CREATE POLICY "Anyone can view moves" 
ON moves FOR SELECT 
USING (true);

CREATE POLICY "Players can insert moves in their games" 
ON moves FOR INSERT 
WITH CHECK (
  EXISTS (
    SELECT 1 FROM games 
    WHERE games.id = game_id 
    AND (games.white_player_id = auth.uid() OR games.black_player_id = auth.uid())
  )
);

-- Game verification policies
CREATE POLICY "Anyone can view game verifications" 
ON game_verifications FOR SELECT 
USING (true);

CREATE POLICY "Players can insert game verifications" 
ON game_verifications FOR INSERT 
WITH CHECK (
  EXISTS (
    SELECT 1 FROM games 
    WHERE games.id = game_id 
    AND (games.white_player_id = auth.uid() OR games.black_player_id = auth.uid())
  )
);
