import { getProfileId } from "./profile";
import type {
  AppSettings,
  BringList,
  BringSettings,
  BringTransfer,
  HistoryEntry,
  HistoryFilter,
  IngredientHit,
  Group,
  ImportJob,
  Ingredient,
  OpenRating,
  Person,
  Plan,
  Rankings,
  Recipe,
  RecipeInput,
  RecipeSummary,
  ShoppingItem,
  Status,
  Tag,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
  get conflict() {
    return this.status === 409;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const profile = getProfileId();
  if (profile !== null) headers["X-Delikatessen-Person"] = String(profile);
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Keine Verbindung. Ändern geht nur mit Netz.");
  }
  if (res.status === 204) return undefined as T;
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    throw new ApiError(res.status, describe(data?.detail) || `Fehler ${res.status}`);
  }
  return data as T;
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d?.msg === "string" ? d.msg.replace(/^Value error, /, "") : ""))
      .filter(Boolean)
      .join(", ");
  }
  return "";
}

const qs = (params: Record<string, string | number | boolean | undefined | null | (string | number)[]>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, String(x)));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  // Rezepte
  recipes: (p: { q?: string; tag?: number[]; size?: string; max_duration?: number; favorite?: boolean } = {}) =>
    request<RecipeSummary[]>("GET", `/recipes${qs(p)}`),
  recipe: (id: number) => request<Recipe>("GET", `/recipes/${id}`),
  createRecipe: (data: RecipeInput) => request<Recipe>("POST", "/recipes", data),
  updateRecipe: (id: number, data: RecipeInput) => request<Recipe>("PUT", `/recipes/${id}`, data),
  patchRecipe: (id: number, data: { favorite?: boolean; excluded?: boolean }) =>
    request<RecipeSummary>("PATCH", `/recipes/${id}`, data),
  deleteRecipe: (id: number) => request<void>("DELETE", `/recipes/${id}`),
  uploadImage: (id: number, file: Blob) => {
    const fd = new FormData();
    fd.append("file", file, "foto");
    return request<RecipeSummary>("POST", `/recipes/${id}/image`, fd);
  },
  deleteImage: (id: number) => request<RecipeSummary>("DELETE", `/recipes/${id}/image`),

  // Katalog
  ingredients: (q?: string) => request<Ingredient[]>("GET", `/ingredients${qs({ q, limit: q ? 30 : 2000 })}`),
  createIngredient: (name: string, group_id?: number | null) =>
    request<Ingredient>("POST", "/ingredients", { name, group_id: group_id ?? null }),
  groups: () => request<Group[]>("GET", "/ingredient-groups"),
  tags: () => request<Tag[]>("GET", "/tags"),
  createTag: (name: string) => request<Tag>("POST", "/tags", { name }),

  // Plan
  plan: (start: string) => request<Plan>("GET", `/plans/${start}`),
  generate: (start: string, version: number) => request<Plan>("POST", `/plans/${start}/generate`, { version }),
  addSlots: (start: string, body: { version: number; first: string; last: string; meal: string; size: string }) =>
    request<Plan>("POST", `/plans/${start}/slots`, body),
  updateSlot: (
    start: string,
    id: number,
    body: {
      version: number;
      recipe_id?: number;
      clear_recipe?: boolean;
      pinned?: boolean;
      cancelled?: boolean;
      not_cooked?: boolean;
      swap_main?: boolean;
    },
  ) => request<Plan>("PUT", `/plans/${start}/slots/${id}`, body),
  deleteSlot: (start: string, id: number, version: number) =>
    request<Plan>("DELETE", `/plans/${start}/slots/${id}${qs({ version })}`),
  suggest: (start: string, id: number, version: number) =>
    request<Plan>("POST", `/plans/${start}/slots/${id}/suggest`, { version }),
  candidates: (start: string, id: number) => request<RecipeSummary[]>("GET", `/plans/${start}/slots/${id}/candidates`),

  // Bewertung
  rate: (slotId: number, personId: number, value: number | null) =>
    request<Record<string, number>>("PUT", `/slots/${slotId}/ratings/${personId}`, { value }),
  openRatings: () => request<OpenRating[]>("GET", "/ratings/open"),
  rankings: () => request<Rankings>("GET", "/rankings"),
  setUseUp: (start: string, version: number, ingredient_ids: number[]) =>
    request<Plan>("PUT", `/plans/${start}/use-up`, { version, ingredient_ids }),
  byIngredients: (ids: number[]) => request<IngredientHit[]>("GET", `/search/by-ingredients${qs({ ids })}`),
  history: (f: HistoryFilter) => request<HistoryEntry[]>("GET", `/history${qs({ ...f })}`),
  pushKey: () => request<{ public_key: string }>("GET", "/push/key"),
  pushSubscribe: (sub: PushSubscriptionJSON) => request<{ id: number }>("POST", "/push/subscriptions", sub),
  pushUnsubscribe: (endpoint: string) => request<void>("DELETE", "/push/subscriptions", { endpoint }),
  pushTest: (endpoint: string) => request<{ gesendet: number }>("POST", "/push/test", { endpoint }),
  runThursday: () => request<{ erzeugt: boolean; woche?: string; gesendet?: number }>("POST", "/push/donnerstagslauf"),

  // Einkauf
  shopping: (start: string) => request<ShoppingItem[]>("GET", `/plans/${start}/shopping`),
  patchShopping: (id: number, data: { checked?: boolean; at_home?: boolean }) =>
    request<ShoppingItem>("PATCH", `/shopping/items/${id}`, data),

  // Import
  startImport: (url: string) => request<ImportJob>("POST", "/imports", { kind: "link", url }),
  startTextImport: (text: string) => request<ImportJob>("POST", "/imports", { kind: "text", text }),
  startPhotoImport: (photos: { file: Blob; rot: number }[]) => {
    const fd = new FormData();
    photos.forEach((p, i) => {
      fd.append("bilder", p.file, `foto-${i}.jpg`);
      // Drehung im Uhrzeigersinn je Foto, in derselben Reihenfolge
      fd.append("drehung", String(p.rot));
    });
    return request<ImportJob>("POST", "/imports/foto", fd);
  },
  importJob: (id: number) => request<ImportJob>("GET", `/imports/${id}`),
  acceptImport: (id: number, recipe: RecipeInput, image_url?: string | null) =>
    request<Recipe>("POST", `/imports/${id}/accept`, { recipe, image_url: image_url ?? null }),

  // Familie und Einstellungen
  persons: () => request<Person[]>("GET", "/persons"),
  createPerson: (p: Omit<Person, "id">) => request<Person>("POST", "/persons", p),
  updatePerson: (id: number, p: Omit<Person, "id">) => request<Person>("PUT", `/persons/${id}`, p),
  deletePerson: (id: number) => request<void>("DELETE", `/persons/${id}`),
  me: () => request<Person | null>("GET", "/me"),
  settings: () => request<AppSettings>("GET", "/settings"),
  saveSettings: (s: AppSettings) => request<AppSettings>("PUT", "/settings", s),
  bring: () => request<BringSettings>("GET", "/bring"),
  saveBring: (enabled: boolean, list?: BringList) =>
    request<BringSettings>("PUT", "/bring", { enabled, list_uuid: list?.uuid ?? null, list_name: list?.name ?? null }),
  bringAccount: (mail: string, password: string) => request<BringList[]>("PUT", "/bring/account", { mail, password }),
  deleteBringAccount: () => request<BringSettings>("DELETE", "/bring/account"),
  bringLists: () => request<BringList[]>("GET", "/bring/lists"),
  sendToBring: (start: string) => request<BringTransfer>("POST", `/plans/${start}/shopping/bring`),
  status: () => request<Status>("GET", "/status"),
};
