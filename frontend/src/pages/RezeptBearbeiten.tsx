import { useNavigate, useParams } from "react-router";
import { api } from "../api";
import { RecipeForm } from "../components/RecipeForm";
import { useToast } from "../components/Toast";
import { errorText, useLoad } from "../lib";

export function RezeptBearbeiten() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const toast = useToast();
  const recipe = useLoad(() => api.recipe(id), [id]);
  if (recipe.error && !recipe.data) return <p className="error page">{recipe.error}</p>;
  if (!recipe.data) return <div className="page" aria-busy="true" />;
  const r = recipe.data;
  return (
    <section className="page">
      <h1>Rezept bearbeiten</h1>
      <RecipeForm
        initial={{
          title: r.title,
          servings: r.servings,
          size: r.size,
          duration_min: r.duration_min,
          steps: r.steps,
          tag_ids: r.tags.map((t) => t.id),
          ingredients: r.ingredients,
          source_url: r.source_url,
          favorite: r.favorite,
          excluded: r.excluded,
        }}
        currentImage={r.image_url}
        submitLabel="Speichern"
        onCancel={() => navigate(-1)}
        onSubmit={async (data, extras) => {
          await api.updateRecipe(r.id, data);
          try {
            if (extras.image) await api.uploadImage(r.id, extras.image);
            else if (extras.removeImage) await api.deleteImage(r.id);
          } catch (e) {
            toast.show(`Gespeichert, aber das Foto nicht: ${errorText(e)}`, { error: true });
          }
          navigate(`/rezepte/${r.id}`, { replace: true });
        }}
      />
    </section>
  );
}
