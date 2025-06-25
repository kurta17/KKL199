-- Create a function for direct user insertion without foreign key constraint
CREATE OR REPLACE FUNCTION public.direct_user_insert(user_data jsonb)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  inserted_user jsonb;
BEGIN
  -- Temporarily disable foreign key constraint checking
  SET session_replication_role = 'replica';
  
  -- Insert the user data directly
  INSERT INTO public.users (
    id, 
    username,
    email,
    public_key,
    rating,
    created_at
  ) VALUES (
    (user_data->>'id')::uuid,
    user_data->>'username',
    user_data->>'email',
    user_data->>'public_key',
    COALESCE((user_data->>'rating')::integer, 1200),
    COALESCE((user_data->>'created_at')::timestamp with time zone, NOW())
  )
  RETURNING to_jsonb(users.*) INTO inserted_user;
  
  -- Re-enable constraint checking
  SET session_replication_role = 'origin';
  
  RETURN inserted_user;
EXCEPTION WHEN OTHERS THEN
  -- Make sure we re-enable constraints even if there's an error
  SET session_replication_role = 'origin';
  RAISE EXCEPTION 'Error in direct_user_insert: %', SQLERRM;
END;
$$;
