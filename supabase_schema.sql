-- Linup cloud schema. Run once in the Supabase dashboard: SQL Editor -> New query.
--
-- One row per (user, investment). `data` holds the investment with its tables,
-- compound sessions and table stats (see linup_sync.export_investment).
-- Deletions are soft (deleted = true) so other devices learn about them.
-- Row Level Security guarantees a user can only ever see/modify their own rows,
-- even though the app ships with the public anon key.

create table if not exists public.investments (
  user_id    uuid        not null default auth.uid()
                         references auth.users (id) on delete cascade,
  id         uuid        not null,
  data       jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null,
  deleted    boolean     not null default false,
  primary key (user_id, id)
);

alter table public.investments enable row level security;

drop policy if exists "own rows: select" on public.investments;
drop policy if exists "own rows: insert" on public.investments;
drop policy if exists "own rows: update" on public.investments;
drop policy if exists "own rows: delete" on public.investments;

create policy "own rows: select" on public.investments
  for select using (user_id = auth.uid());
create policy "own rows: insert" on public.investments
  for insert with check (user_id = auth.uid());
create policy "own rows: update" on public.investments
  for update using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "own rows: delete" on public.investments
  for delete using (user_id = auth.uid());

create index if not exists investments_user_updated
  on public.investments (user_id, updated_at);
