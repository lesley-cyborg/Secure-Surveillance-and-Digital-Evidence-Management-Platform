export type RoleOption = {
  id: string;
  name: string;
};

/**
 * System roles from public.roles (Docker/test DB).
 * Replace PASTE_* with full UUIDs from:
 *   SELECT name, id::text FROM public.roles;
 */
export const ROLE_OPTIONS: RoleOption[] = [
  {
    id: "e9d22953-d2b1-4976-87e2-7e7cae9349c2", // e9d22953-d2b1-4976-87e2-...
    name: "ADMINISTRATOR",
  },
  {
    id: "35789b80-a56e-4dee-9e80-c131e534eeaf", // 35789b80-a56e-4dee-9e80-...
    name: "INVESTIGATOR",
  },
  {
    id: "97295a86-12b3-4cdf-b504-5bcbc4d90153", // 97295a86-12b3-4cdf-b504-...
    name: "SECURITY_OFFICER",
  },
  {
    id: "c5807e22-167c-4c0f-80a5-baf74307c9b5", // c5807e22-167c-4c0f-80a5-...
    name: "SECURITY_MANAGER",
  },
];