/*
This SQL script provides a procedure that you can use to confirm any user's email.
Run this in the Supabase SQL Editor to add the procedure to your database.
Then you can call it with any email address.

Example usage:
CALL confirm_user_email('user@example.com');
*/

CREATE OR REPLACE PROCEDURE confirm_user_email(user_email TEXT)
LANGUAGE plpgsql
AS $$
DECLARE
  user_id uuid;
BEGIN
  -- Get the user ID based on email
  SELECT id INTO user_id FROM auth.users WHERE email = user_email;
  
  IF user_id IS NULL THEN
    RAISE EXCEPTION 'User with email % not found', user_email;
  END IF;
  
  -- Update the email_confirmed_at field to mark email as confirmed
  UPDATE auth.users
  SET email_confirmed_at = NOW()
  WHERE id = user_id;
  
  RAISE NOTICE 'Email confirmed for user % with email %', user_id, user_email;
END $$;
