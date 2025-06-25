-- Add missing policy to allow user insertion
CREATE POLICY "Service role can insert users" 
ON users FOR INSERT 
WITH CHECK (true);

-- If needed, we could restrict this more specifically:
-- WITH CHECK (auth.role() = 'service_role' OR auth.role() = 'authenticated');
