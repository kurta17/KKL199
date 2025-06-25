-- SQL script to fix foreign key constraints and improve database structure
-- This script addresses common issues with Supabase auth and public schema relationships

-- Step 1: Fix the users table constraint
-- First drop the existing constraint
ALTER TABLE IF EXISTS public.users 
  DROP CONSTRAINT IF EXISTS users_id_fkey;

-- Step 2: Create a trigger to automatically create public.users records when auth.users are created
CREATE OR REPLACE FUNCTION public.handle_new_user() 
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, username, email, public_key, rating)
  VALUES (
    NEW.id, 
    COALESCE(NEW.raw_user_meta_data->>'username', 'user_' || substr(NEW.id::text, 1, 8)),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'public_key', '0x' || repeat('0', 40)),
    1200
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Drop the trigger if it exists
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

-- Create the trigger
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Step 3: Create a RLS policy that allows the service role to create users directly
DROP POLICY IF EXISTS "Service role can create users" ON public.users;
CREATE POLICY "Service role can create users" ON public.users 
  FOR INSERT TO service_role 
  WITH CHECK (true);

-- Step 4: Create a policy to allow service role to update users
DROP POLICY IF EXISTS "Service role can update users" ON public.users;
CREATE POLICY "Service role can update users" ON public.users 
  FOR UPDATE TO service_role 
  USING (true);

-- Step 5: Fix the foreign key by re-adding it but with ON DELETE CASCADE
-- Uncomment the line below if you want to enforce referential integrity strongly
-- ALTER TABLE public.users
--   ADD CONSTRAINT users_id_fkey
--   FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Step 6: Fix any orphaned users (public.users entries without auth.users counterparts)
-- This is dangerous to run blindly - only do this for development
-- DELETE FROM public.users
--   WHERE id NOT IN (SELECT id FROM auth.users);

-- For games table, either cascade delete or set NULL
ALTER TABLE IF EXISTS public.games DROP CONSTRAINT IF EXISTS games_white_player_id_fkey;
ALTER TABLE IF EXISTS public.games DROP CONSTRAINT IF EXISTS games_black_player_id_fkey;

-- Re-add with appropriate cascade action
ALTER TABLE public.games
  ADD CONSTRAINT games_white_player_id_fkey
  FOREIGN KEY (white_player_id) REFERENCES public.users(id) ON DELETE SET NULL;
  
ALTER TABLE public.games
  ADD CONSTRAINT games_black_player_id_fkey
  FOREIGN KEY (black_player_id) REFERENCES public.users(id) ON DELETE SET NULL;

-- Success message
DO $$ 
BEGIN
  RAISE NOTICE 'Success! Your database constraints have been updated.';
  RAISE NOTICE 'A trigger has been added to automatically create public.users records.';
  RAISE NOTICE 'RLS policies have been updated to allow proper access control.';
END $$;
