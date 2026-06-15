create extension if not exists pgcrypto;

create table if not exists runs (
  id uuid primary key default gen_random_uuid(),
  run_date date not null,
  product text not null,
  source text,
  created_at timestamptz default now()
);

create table if not exists articles (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references runs(id),
  record_kind text default 'article',
  article_date date,
  product text not null,
  outlet text,
  title text not null,
  url text,
  body_r2_key text,
  body_sha256 text,
  body_head_sha256 text,
  py_tags jsonb default '{}'::jsonb,
  flash_tags jsonb default '{}'::jsonb,
  relevance_score numeric default 0,
  tag_status text default 'pending',
  tag_source text,
  flash_tagged_at timestamptz,
  created_at timestamptz default now(),
  unique(url)
);

create table if not exists brief_requests (
  id uuid primary key default gen_random_uuid(),
  product text not null,
  date_from date not null,
  date_to date not null,
  selected_temas jsonb default '[]',
  selected_empresas_sectores jsonb default '[]',
  selected_entidades jsonb default '[]',
  selected_regiones jsonb default '[]',
  relevance_mode text default 'amplio',
  created_at timestamptz default now()
);

create table if not exists analyzer_packets (
  id uuid primary key default gen_random_uuid(),
  request_id uuid references brief_requests(id),
  product text not null,
  date_from date not null,
  date_to date not null,
  packet_r2_key text,
  packet_preview text,
  article_count int,
  created_at timestamptz default now()
);

create table if not exists briefings (
  id uuid primary key default gen_random_uuid(),
  packet_id uuid references analyzer_packets(id),
  product text not null,
  briefing_md text,
  briefing_html_r2_key text,
  briefing_pdf_r2_key text,
  created_at timestamptz default now()
);

create table if not exists proposed_terms (
  id uuid primary key default gen_random_uuid(),
  article_id uuid references articles(id),
  category text,
  proposed_term text,
  reason text,
  status text default 'pending',
  created_at timestamptz default now()
);
