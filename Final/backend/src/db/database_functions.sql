-- Database functions for improved game handling and player statistics
-- These functions help with foreign key constraints and statistics updates

-- Function to insert a game while bypassing foreign key checks
-- This is for development/demo use only
CREATE OR REPLACE FUNCTION public.insert_game_bypass_checks(game_data jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  inserted_game jsonb;
BEGIN
  -- Check if the players exist, create them if they don't
  BEGIN
    IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = (game_data->>'white_player_id')::uuid) THEN
      INSERT INTO public.users (
        id, 
        username, 
        email, 
        public_key, 
        rating
      ) VALUES (
        (game_data->>'white_player_id')::uuid,
        'player_' || substring((game_data->>'white_player_id'), 1, 8),
        'player_' || substring((game_data->>'white_player_id'), 1, 8) || '@demo.com',
        '0x' || repeat('0', 40),
        1200
      );
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = (game_data->>'black_player_id')::uuid) THEN
      INSERT INTO public.users (
        id, 
        username, 
        email, 
        public_key, 
        rating
      ) VALUES (
        (game_data->>'black_player_id')::uuid,
        'player_' || substring((game_data->>'black_player_id'), 1, 8),
        'player_' || substring((game_data->>'black_player_id'), 1, 8) || '@demo.com',
        '0x' || repeat('0', 40),
        1200
      );
    END IF;
  EXCEPTION WHEN OTHERS THEN
    RAISE LOG 'Error creating players: %', SQLERRM;
  END;

  -- Insert the game using the data provided
  INSERT INTO public.games (
    id,
    white_player_id,
    black_player_id,
    status,
    result,
    created_at,
    started_at,
    completed_at
  ) VALUES (
    (game_data->>'id')::uuid,
    (game_data->>'white_player_id')::uuid,
    (game_data->>'black_player_id')::uuid,
    game_data->>'status',
    (game_data->>'result')::jsonb,
    (game_data->>'created_at')::timestamp with time zone,
    (game_data->>'started_at')::timestamp with time zone,
    (game_data->>'completed_at')::timestamp with time zone
  )
  RETURNING to_jsonb(games.*) INTO inserted_game;

  RETURN inserted_game;
EXCEPTION WHEN OTHERS THEN
  RAISE EXCEPTION 'Error in insert_game_bypass_checks: %', SQLERRM;
END;
$$;

-- Function to increment a player's win count
CREATE OR REPLACE FUNCTION public.increment_win(user_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE public.users
  SET wins = wins + 1, rating = rating + 10
  WHERE id = user_id;
END;
$$;

-- Function to increment a player's loss count
CREATE OR REPLACE FUNCTION public.increment_loss(user_id uuid)
RETURNS void
LANGUAGE PLPGSQL
SECURITY DEFINER
AS $$
BEGIN
  UPDATE public.users
  SET losses = losses + 1, rating = GREATEST(1000, rating - 8)
  WHERE id = user_id;
END;
$$;

-- Function to increment a player's draw count
CREATE OR REPLACE FUNCTION public.increment_draw(user_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE public.users
  SET draws = draws + 1, rating = rating + 2
  WHERE id = user_id;
END;
$$;

-- Function to ensure a user exists (create if not)
CREATE OR REPLACE FUNCTION public.ensure_user_exists(
  p_id uuid,
  p_username text DEFAULT NULL,
  p_email text DEFAULT NULL,
  p_public_key text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_username text;
  v_email text;
  v_public_key text;
BEGIN
  -- Check if the user exists
  IF EXISTS (SELECT 1 FROM public.users WHERE id = p_id) THEN
    RETURN p_id;
  END IF;
  
  -- Set default values if not provided
  v_username := COALESCE(p_username, 'player_' || substring(p_id::text, 1, 8));
  v_email := COALESCE(p_email, 'player_' || substring(p_id::text, 1, 8) || '@demo.com');
  v_public_key := COALESCE(p_public_key, '0x' || repeat('0', 40));
  
  -- Insert the user
  INSERT INTO public.users (
    id,
    username,
    email,
    public_key,
    rating
  ) VALUES (
    p_id,
    v_username,
    v_email,
    v_public_key,
    1200
  );
  
  RETURN p_id;
EXCEPTION WHEN OTHERS THEN
  RAISE LOG 'Error in ensure_user_exists: %', SQLERRM;
  RETURN p_id;
END;
$$;
