-- EMERGENCY BYPASS FIX
-- This SQL script enables the bypass authentication to work

-- Step 1: Install UUID extension if not already installed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Step 2: Remove any foreign key constraint on the users table
ALTER TABLE IF EXISTS public.users 
  DROP CONSTRAINT IF EXISTS users_id_fkey;

-- Step 3: Set a default UUID generation for the id column
ALTER TABLE IF EXISTS public.users 
  ALTER COLUMN id SET DEFAULT uuid_generate_v4();

-- Step 4: Remove all RLS policies that might be blocking inserts
DROP POLICY IF EXISTS "Users can view any user profile" ON public.users;
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;
DROP POLICY IF EXISTS "Demo mode - open access to users" ON public.users;
DROP POLICY IF EXISTS "Emergency open access policy" ON public.users;
DROP POLICY IF EXISTS "Emergency insert policy" ON public.users;
DROP POLICY IF EXISTS "Emergency update policy" ON public.users;

-- Step 5: Create completely open policies for development
CREATE POLICY IF NOT EXISTS "Bypass mode - anyone can view users" ON public.users 
  FOR SELECT USING (true);
  
CREATE POLICY IF NOT EXISTS "Bypass mode - anyone can insert users" ON public.users 
  FOR INSERT WITH CHECK (true);
  
CREATE POLICY IF NOT EXISTS "Bypass mode - anyone can update users" ON public.users 
  FOR UPDATE USING (true);

-- Step 6: Ensure RLS is enabled but with our open policies
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
