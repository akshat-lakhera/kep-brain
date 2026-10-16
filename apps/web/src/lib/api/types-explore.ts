// Types of the Explore routes (/v1/people, /v1/sigs, /v1/changes). Field names follow the API exactly.
import type { Finding, KepCard, PersonRef } from "./types";

export interface PersonRole {
  org: string;
  org_kind: string | null;
  role: string;
  valid_from_iso: string | null;
  source_url: string | null;
}

export interface PersonDecision {
  key: string;
  kind: string;
  summary: string | null;
  kep_number: number | null;
  kep_title: string | null;
  role: string;
  decided_at_iso: string | null;
  url: string | null;
}

export interface OwnersEntry {
  directory: string;
  role: string;
  via_alias: string | null;
  source_url: string | null;
}

export interface Connectivity {
  score: number;
  rank: number;
  of: number;
  method: string;
}

/** GET /v1/people/{login} */
export interface PersonOut {
  login: string;
  url: string;
  is_bot: boolean;
  roles: PersonRole[];
  keps: {
    authored: KepCard[];
    reviews: KepCard[];
    approves: KepCard[];
    prr_approved: { stage: string | null; kep: KepCard }[];
  };
  decisions: PersonDecision[];
  owners: OwnersEntry[];
  connectivity: Connectivity | null;
}

/** One entry of GET /v1/sigs */
export interface SigCard {
  key: string;
  display_name: string | null;
  mission: string | null;
  in_scope: boolean;
  url: string | null;
  keps: number;
  open_findings: number;
  chairs: PersonRef[];
  tech_leads: PersonRef[];
}

/** GET /v1/sigs/{key}: the card with `keps` as the full list instead of the count. */
export interface SigDetail extends Omit<SigCard, "keps"> {
  subprojects: { name: string; url: string | null }[];
  keps_by_status: Record<string, number>;
  keps: KepCard[];
  people: { login: string; url: string; roles: string[] }[];
  findings: Finding[];
}

