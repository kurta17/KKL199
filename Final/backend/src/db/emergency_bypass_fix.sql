-- EMERGENCY BYPASS FIX (MINIMAL VERSION)
-- This SQL script provides the absolute minimum changes needed for the bypass system to work

-- Step 1: Remove the foreign key constraint that's causing issues
ALTER TABLE public.users DROP CONSTRAINT IF EXISTS users_id_fkey;

-- Step 2: Enable row-level security but with completely open policies for development
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Step 3: Remove any existing policies that might be blocking operations
DROP POLICY IF EXISTS "Users can insert their own profile" ON public.users;
DROP POLICY IF EXISTS "Users can view any user profile" ON public.users;
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;

-- Step 4: Create completely open policies for development
CREATE POLICY "Bypass - Open Select" ON public.users FOR SELECT USING (true);
CREATE POLICY "Bypass - Open Insert" ON public.users FOR INSERT WITH CHECK (true);
CREATE POLICY "Bypass - Open Update" ON public.users FOR UPDATE USING (true);

-- Step 5: Add a message to confirm this was run
DO $$
BEGIN
    RAISE NOTICE 'Emergency bypass fix applied successfully!';
END $$;
