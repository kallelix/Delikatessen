import { expect, test, type BrowserContext, type Page } from "@playwright/test";

// Hauptabläufe in Smartphone-Größe, nacheinander auf einer frischen Datenbank
test.describe.configure({ mode: "serial" });

let context: BrowserContext;
let page: Page;
const shots = (name: string) => page.screenshot({ path: `test-results/screens/${name}.png`, fullPage: true });

test.beforeAll(async ({ browser }, info) => {
  context = await browser.newContext({ ...info.project.use, permissions: ["clipboard-read", "clipboard-write"] });
  page = await context.newPage();
});

test.afterAll(async () => {
  await context.close();
});

test("Erststart: erste erwachsene Person anlegen", async () => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Willkommen bei Delikatessen" })).toBeVisible();
  await shots("01-willkommen");
  await page.getByLabel("Dein Name").fill("Anna");
  await page.getByRole("button", { name: "Loslegen" }).click();
  await expect(page.getByRole("navigation", { name: "Hauptnavigation" })).toBeVisible();
  await expect(page.locator(".slot")).toHaveCount(9);
});

test("Familie: Kind mit No-go-Gruppe hinzufügen", async () => {
  await page.getByRole("link", { name: "Mehr" }).click();
  await page.getByRole("link", { name: "Familie" }).click();
  await page.getByRole("button", { name: "Person hinzufügen" }).click();
  const sheet = page.getByRole("dialog");
  await sheet.getByLabel("Name").fill("Ida");
  await sheet.getByRole("radio", { name: "Kind" }).click();
  await expect(sheet.getByLabel("Portionsfaktor (1 = ganze Portion)")).toHaveValue("0,5");
  await sheet.getByLabel("Ganze Gruppe als No-go").selectOption({ label: "Nüsse" });
  await expect(sheet.getByRole("button", { name: "Nüsse (Gruppe) entfernen" })).toBeVisible();
  await sheet.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("No-go: Nüsse (Gruppe)")).toBeVisible();
  await shots("02-familie");
});

async function createRecipe(title: string, size: "Hauptmahlzeit" | "Kleine Mahlzeit", ingredients: [string, string, string][]) {
  await page.goto("/neu");
  await page.getByRole("button", { name: "Von Hand anlegen" }).click();
  await page.getByLabel("Titel").fill(title);
  await page.getByRole("radio", { name: size }).click();
  await page.getByLabel("Dauer (Minuten)").fill("30");
  for (let i = 0; i < ingredients.length; i++) {
    const [amount, unit, name] = ingredients[i];
    if (i > 0) await page.getByRole("button", { name: "Zutat", exact: true }).click();
    await page.getByLabel(`Menge Zutat ${i + 1}`).fill(amount);
    await page.getByLabel(`Einheit Zutat ${i + 1}`).selectOption(unit);
    await page.getByLabel(`Name Zutat ${i + 1}`).fill(name);
    await page.getByRole("button", { name: "Nicht zugeordnet · zuordnen" }).first().click();
    await page.getByRole("option").getByRole("button").first().click();
  }
  await page.getByLabel("Zubereitung (ein Schritt pro Zeile)").fill("Vorbereiten\nKochen\nServieren");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
}

test("Rezepte von Hand anlegen, mit Zuordnung zum Katalog", async () => {
  await createRecipe("Kartoffelgratin", "Hauptmahlzeit", [
    ["1,2", "kg", "Kartoffel"],
    ["400", "ml", "Sahne"],
  ]);
  await shots("03-rezept");
  // Portionen umrechnen (F-02)
  await page.getByRole("button", { name: "Mehr Portionen" }).click();
  await page.getByRole("button", { name: "Mehr Portionen" }).click();
  await expect(page.locator(".ingredients li").first()).toContainText("1,8 kg");
  await createRecipe("Nudeln mit Pesto", "Hauptmahlzeit", [["500", "g", "Spaghetti"]]);
  await createRecipe("Walnussbrot", "Kleine Mahlzeit", [["100", "g", "Walnuss"]]);
  await createRecipe("Obstsalat", "Kleine Mahlzeit", [["2", "Stück", "Apfel"]]);

  await page.getByRole("link", { name: "Rezepte" }).click();
  await page.getByLabel("Rezepte durchsuchen").fill("sahne");
  await expect(page.locator(".recipe-card")).toHaveCount(1);
  await expect(page.locator(".recipe-card")).toContainText("Kartoffelgratin");
});

test("Plan erzeugen, fixieren, neu vorschlagen, Essen entfällt", async () => {
  await page.getByRole("link", { name: "Woche" }).click();
  await page.getByRole("button", { name: "Plan erzeugen" }).click();
  await expect(page.getByText("Plan erzeugt")).toBeVisible();
  // Walnussbrot fällt wegen Idas No-go raus, also nur Obstsalat als kleine Mahlzeit
  await expect(page.locator(".slot", { hasText: "Walnussbrot" })).toHaveCount(0);
  await expect(page.locator(".slot.small", { hasText: "Obstsalat" })).toHaveCount(2);
  await shots("04-woche");

  const first = page.locator(".slot.main").first();
  await first.click();
  await page.getByRole("button", { name: "Fixieren" }).click();
  await expect(first.locator(".pin")).toBeVisible();

  const second = page.locator(".slot.main").nth(1);
  const before = await second.locator(".slot-title").innerText();
  await second.click();
  await page.getByRole("button", { name: "Neuer Vorschlag" }).click();
  await expect(second.locator(".slot-title")).not.toHaveText(before);

  const third = page.locator(".slot.main").nth(2);
  await third.click();
  await page.getByRole("button", { name: "Essen entfällt" }).click();
  await expect(third).toHaveClass(/cancelled/);
});

test("Einkaufsliste: abhaken, im Haus, als Text teilen", async () => {
  await page.getByRole("button", { name: "Zutaten einkaufen" }).click();
  await expect(page.getByRole("heading", { name: "Einkauf" })).toBeVisible();
  const rows = page.locator(".shop-row");
  await expect(rows.first()).toBeVisible();
  await shots("05-einkauf");
  await rows.first().getByRole("checkbox").check();
  await expect(rows.first()).toHaveClass(/checked/);
  const name = await rows.nth(1).locator(".shop-text span").first().innerText();
  await rows.nth(1).getByRole("button", { name: /schon im Haus/ }).click();
  await expect(page.getByText(/Schon im Haus \(1\)/)).toBeVisible();
  await page.evaluate(() => Object.defineProperty(navigator, "share", { value: undefined, configurable: true }));
  await page.getByRole("button", { name: "Als Text teilen" }).click();
  await expect(page.getByText("Liste kopiert")).toBeVisible();
  const text = await page.evaluate(() => navigator.clipboard.readText());
  expect(text).toContain("Einkauf für die Woche ab");
  expect(text).not.toContain(name);
});

test("Kochansicht mit großen Schritten", async () => {
  await page.goto("/rezepte");
  await page.locator(".recipe-card", { hasText: "Kartoffelgratin" }).click();
  await page.getByRole("link", { name: "Kochen starten" }).click();
  await expect(page.getByText("Schritt 1 von 3")).toBeVisible();
  await page.getByRole("button", { name: "Weiter" }).click();
  await expect(page.locator(".cook-text")).toHaveText("Kochen");
  await shots("06-kochen");
  await page.getByRole("button", { name: "Kochansicht schließen" }).click();
});

test("Link-Import endet in der Vorschau", async () => {
  await page.goto("/neu");
  await page.getByPlaceholder("https://…").fill("http://127.0.0.1:8766/rezeptseiten/02_graph.html");
  await page.getByRole("button", { name: "Rezept lesen" }).click();
  await expect(page.getByRole("heading", { name: "Import prüfen" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Titel")).toHaveValue("Spaghetti Bolognese");
  await shots("07-import");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByRole("heading", { name: "Spaghetti Bolognese" })).toBeVisible();
});

test("AK-07: Teilen-Menü öffnet die Importvorschau", async () => {
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  // So schickt Chrome einen geteilten Link an das Teilen-Ziel aus dem Manifest
  await page.evaluate(() => {
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/teilen";
    form.enctype = "multipart/form-data";
    const add = (name: string, value: string) => {
      const i = document.createElement("input");
      i.name = name;
      i.value = value;
      form.appendChild(i);
    };
    add("title", "Linsensuppe");
    add("text", "Schau mal: http://127.0.0.1:8766/rezeptseiten/03_liste.html");
    add("url", "");
    document.body.appendChild(form);
    form.submit();
  });
  await expect(page.getByRole("heading", { name: "Import prüfen" })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByLabel("Titel")).toHaveValue("Linsensuppe");
});

test("AK-09: Plan und Rezepte der Woche ohne Netz lesbar", async () => {
  await page.goto("/");
  await expect(page.locator(".slot").first()).toBeVisible();
  // Rezepte der Woche werden im Hintergrund vorgeladen
  await page.waitForTimeout(1500);
  const title = await page.locator(".slot.main:not(.cancelled) .slot-title").first().innerText();
  await context.setOffline(true);
  try {
    await page.reload();
    await expect(page.getByText("Ohne Netz")).toBeVisible();
    await expect(page.locator(".slot").first()).toBeVisible();
    await page.locator(".slot.main:not(.cancelled)").first().click();
    await page.getByRole("button", { name: "Rezept ansehen" }).click();
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await shots("08-offline");
  } finally {
    await context.setOffline(false);
  }
});

test("Bewerten durch Eltern auch fürs Kind", async () => {
  // Rezept auf einen vergangenen Platz der Vorwoche legen und dort bewerten
  await page.goto("/");
  await page.getByRole("button", { name: "Woche davor" }).click();
  await page.locator(".slot.main").first().click();
  await page.getByRole("button", { name: "Rezept wählen" }).click();
  await page.getByRole("dialog").getByRole("button", { name: /Kartoffelgratin/ }).click();
  await page.locator(".slot.main").first().click();
  await page.getByRole("button", { name: "Bewerten" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("group", { name: "Wertung von Anna" }).getByRole("button", { name: "lecker" }).click();
  await dialog.getByRole("group", { name: "Wertung von Ida" }).getByRole("button", { name: "okay" }).click();
  await expect(dialog.getByRole("group", { name: "Wertung von Ida" }).getByRole("button", { name: "okay" })).toHaveAttribute("aria-pressed", "true");
  await shots("09-bewerten");
  await dialog.getByRole("button", { name: "Fertig" }).click();
  await page.goto("/mehr/rangliste");
  await expect(page.locator(".ranking li").first()).toContainText("Kartoffelgratin");
});
