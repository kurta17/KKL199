/*
This SQL script is for development purposes only.
It allows you to confirm a user's email without requiring them to click a verification link.
Run this in the Supabase SQL Editor to verify an email address.
*/

-- Replace 'user_email_here@example.com' with the actual email you want to verify
DO $$
DECLARE
  user_id uuid;
BEGIN
  -- Get the user ID based on email
  SELECT id INTO user_id FROM auth.users WHERE email = 'testuser4@gmail.com';
  
  IF user_id IS NULL THEN
    RAISE EXCEPTION 'User with email testuser4@gmail.com not found';
  END IF;
  
  -- Update the email_confirmed_at field to mark email as confirmed
  UPDATE auth.users
  SET email_confirmed_at = NOW()
  WHERE id = user_id;
  
  RAISE NOTICE 'Email confirmed for user %', user_id;
END $$;

-- Query to verify the update was successful
SELECT id, email, email_confirmed_at 
FROM auth.users 
WHERE email = 'testuser4@gmail.com';
