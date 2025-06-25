DROP POLICY IF EXISTS "Anyone can insert users" ON public.users; CREATE POLICY "Anyone can insert users" ON public.users FOR INSERT WITH CHECK (true);
