-- Complete Fix for User Registration Foreign Key Constraint Issues

-- Step 1: Create appropriate RLS policies
ALTER TABLE IF EXISTS public.users ENABLE ROW LEVEL SECURITY;

-- Drop any existing conflicting policies
DROP POLICY IF EXISTS "Anyone can insert users" ON public.users;
DROP POLICY IF EXISTS "Service role can insert users" ON public.users;
DROP POLICY IF EXISTS "Service role can do anything" ON public.users;
DROP POLICY IF EXISTS "Users can see own data" ON public.users;
DROP POLICY IF EXISTS "Development mode - anyone can insert users" ON public.users;

-- Create policies for user management
CREATE POLICY "Service role can do anything" ON public.users
  USING (auth.role() = 'service_role');

CREATE POLICY "Users can see own data" ON public.users
  FOR SELECT
  USING (auth.uid() = id);

CREATE POLICY "Anyone can insert users" ON public.users
  FOR INSERT
  WITH CHECK (true);

-- Step 2: Add function to auto-create user profile after signup
-- This function will handle the "foreign key constraint" issue automatically
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.users (id, username, email, public_key, rating, created_at, updated_at)
  VALUES (
    NEW.id, 
    COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1)),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'public_key', '0x0'),
    1200,
    NOW(),
    NOW()
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Step 3: Add trigger to automatically run when user is confirmed
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Step 4: Make sure users table has the right constraints
-- Note: This assumes the existing structure is correct, it just verifies it
DO $$ 
BEGIN
  -- Check if the foreign key constraint exists
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'users_id_fkey'
  ) THEN
    -- Add constraint if missing
    ALTER TABLE public.users
    ADD CONSTRAINT users_id_fkey
    FOREIGN KEY (id) REFERENCES auth.users(id);
  END IF;
END
$$;
