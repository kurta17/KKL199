-- DEMO MODE - Quick Fix for Foreign Key Constraint Issue

-- This SQL file will disable the foreign key constraint between users table and auth.users
-- This is for DEMO PURPOSES ONLY and should not be used in production

-- Step 1: Drop the foreign key constraint
ALTER TABLE IF EXISTS public.users 
  DROP CONSTRAINT IF EXISTS users_id_fkey;

-- Step 2: Set up loose permissions for demo mode
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Step 3: Drop any existing policies (to avoid conflicts)
DROP POLICY IF EXISTS "Anyone can insert users" ON public.users;
DROP POLICY IF EXISTS "Service role can insert users" ON public.users;
DROP POLICY IF EXISTS "Service role can do anything" ON public.users;
DROP POLICY IF EXISTS "Users can see own data" ON public.users;
DROP POLICY IF EXISTS "Development mode - anyone can insert users" ON public.users;

-- Step 4: Create open policies for the demo
CREATE POLICY "Demo mode - open access to users" ON public.users USING (true);

-- Step 5: Optional - add a UUID extension if not already available
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Step 6: Modify the users table to make the id column accept any UUID
-- This is done by making it default to a random UUID if none is provided
ALTER TABLE public.users 
  ALTER COLUMN id SET DEFAULT uuid_generate_v4();

-- Success message
DO $$ 
BEGIN
  RAISE NOTICE 'Success! Your database is now in demo mode with constraints removed.';
  RAISE NOTICE 'Registration should work without foreign key errors now.';
  RAISE NOTICE 'IMPORTANT: This configuration should not be used in production!';
END $$;
