-- Fix Foreign Key Constraint Issue and RLS Policy for the users Table

-- First, enable Row Level Security for the users table if not already enabled
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Drop any existing insert policies to avoid conflicts
DROP POLICY IF EXISTS "Anyone can insert users" ON public.users;
DROP POLICY IF EXISTS "Service role can insert users" ON public.users;

-- Create a policy that allows the service role to insert users
CREATE POLICY "Service role can insert users" ON public.users
  FOR INSERT
  WITH CHECK (auth.role() = 'service_role');

-- Create a policy that enables service_role to do all operations
CREATE POLICY "Service role can do anything" ON public.users
  USING (auth.role() = 'service_role');

-- Add a policy that lets authenticated users see their own data
CREATE POLICY "Users can see own data" ON public.users
  FOR SELECT
  USING (auth.uid() = id);

-- Commit the changes
COMMIT;
