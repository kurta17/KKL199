-- This SQL can be run in the Supabase SQL editor
-- It adds a policy that allows anyone to insert into the 'users' table

-- First check if the policy already exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE schemaname = 'public'
        AND tablename = 'users'
        AND policyname = 'Anyone can insert users'
    ) THEN
        -- Create the policy if it doesn't exist
        EXECUTE 'CREATE POLICY "Anyone can insert users" ON public.users FOR INSERT WITH CHECK (true);';
        RAISE NOTICE 'Policy created successfully.';
    ELSE
        RAISE NOTICE 'Policy already exists. No action taken.';
    END IF;
END $$;

-- You can also check existing policies with:
-- SELECT * FROM pg_policies WHERE schemaname = 'public' AND tablename = 'users';
