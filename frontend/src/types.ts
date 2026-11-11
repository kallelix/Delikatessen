export type Size = "haupt" | "klein";
export type Meal = "mittag" | "abend";

export interface Tag {
  id: number;
  name: string;
}

export interface Group {
  id: number;
  name: string;
}

export interface Ingredient {
  id: number;
  name: string;
  group_id: number | null;
  group: string | null;
  default_unit: string | null;
  aliases: string[];
}

export interface RecipeIngredient {
  amount: number | null;
  unit: string | null;
  name: string;
  note: string | null;
  ingredient_id: number | null;
  ingredient_name?: string | null;
}

export interface RecipeSummary {
  id: number;
  title: string;
  size: Size;
  duration_min: number | null;
  image_url: string | null;
  favorite: boolean;
  excluded: boolean;
  plannable: boolean;
  tags: Tag[];
}

export interface Recipe extends RecipeSummary {
  servings: number;
  steps: string[];
  ingredients: RecipeIngredient[];
  source_url: string | null;
  favorite_score: number;
  cooked_count: number;
  last_cooked: string | null;
  cooked_dates: string[];
}

export interface RecipeInput {
  title: string;
  servings: number;
  size: Size;
  duration_min: number | null;
  steps: string[];
  tag_ids: number[];
  ingredients: RecipeIngredient[];
  source_url: string | null;
  favorite: boolean;
  excluded: boolean;
}

export interface NoGo {
  ingredient_id?: number | null;
  group_id?: number | null;
  name?: string;
}

export interface Person {
  id: number;
  name: string;
  kind: "erwachsen" | "kind";
  portion_factor: number;
  active: boolean;
  netbird_ip: string | null;
  nogos: NoGo[];
}

export interface SlotRecipe {
  id: number;
  title: string;
  image_url: string | null;
  duration_min: number | null;
  size: Size;
}

export interface Slot {
  id: number;
  date: string;
  meal: Meal;
  size: Size;
  extra: boolean;
  recipe: SlotRecipe | null;
  pinned: boolean;
  cancelled: boolean;
  not_cooked: boolean;
  reason: string | null;
  cooked: boolean;
  rateable: boolean;
  ratings: Record<string, number>;
}

export interface Plan {
  start: string;
  end: string;
  version: number;
  status: string;
  slots: Slot[];
}

export interface OpenRating {
  slot_id: number;
  date: string;
  meal: Meal;
  recipe: SlotRecipe;
  missing_person_ids: number[];
}

export interface RankingEntry {
  recipe: RecipeSummary;
  favorite_score: number;
  ratings: number;
  cooked_count: number;
  last_cooked: string | null;
}

export interface Rankings {
  ranking: RankingEntry[];
  long_not_eaten: RankingEntry[];
}

export interface ShoppingItem {
  id: number;
  name: string;
  group: string;
  amount: number | null;
  unit: string | null;
  quantity: string;
  recipes: string[];
  checked: boolean;
  at_home: boolean;
}

export interface PreviewIngredient extends RecipeIngredient {
  line: string;
}

export interface ImportResult {
  title?: string | null;
  servings?: number;
  duration_min?: number | null;
  size?: Size;
  steps?: string[];
  ingredients?: PreviewIngredient[];
  image_url?: string | null;
  source_url?: string;
}

export interface ImportJob {
  id: number;
  kind: string;
  source: string;
  status: "wartet" | "laeuft" | "fertig" | "ohne_schema" | "fehler" | "uebernommen";
  result: ImportResult | null;
  error: string | null;
  recipe_id: number | null;
}

export interface Weights {
  F: number;
  L: number;
  T: number;
  A: number;
}

export interface AppSettings {
  grid: Record<string, Meal[]>;
  weekend_main: Meal;
  time_limits: Record<string, number | null>;
  weights: Weights;
  plan_time: string;
}
