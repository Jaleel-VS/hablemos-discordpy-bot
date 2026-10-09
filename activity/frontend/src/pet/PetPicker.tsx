// PetPicker: first-visit onboarding and critter re-customisation.
// Species chips (tiny 40 px Pet previews), 8 colour swatches, name input,
// live 120 px preview. All copy is Spanish to match the hub.
import { useState } from "react";
import type { PetChoice, PetState } from "../api";
import { choosePet } from "../api";
import Pet from "./Pet";
import { SPECIES, SPECIES_NAMES, type Species } from "./model";

const SWATCHES = [
  "#5fc9b5",
  "#f28c6a",
  "#8fa8ff",
  "#7ccf6a",
  "#c9a0ff",
  "#ffd166",
  "#ff8fab",
  "#9be7ff",
];

const SWATCH_LABELS: Record<string, string> = {
  "#5fc9b5": "turquesa",
  "#f28c6a": "salmón",
  "#8fa8ff": "lavanda",
  "#7ccf6a": "verde",
  "#c9a0ff": "violeta",
  "#ffd166": "amarillo",
  "#ff8fab": "rosa",
  "#9be7ff": "celeste",
};

interface PetPickerProps {
  accessToken: string;
  /** Pre-filled values when editing an existing pet. */
  initial?: { species: Species; color: string; name: string };
  /** Called with the fresh PetState after a successful save. */
  onDone: (state: PetState) => void;
  /** Offered only when editing; the card restores the state it already had. */
  onCancel?: () => void;
}

export default function PetPicker({ accessToken, initial, onDone, onCancel }: PetPickerProps) {
  const [species, setSpecies] = useState<Species>(initial?.species ?? "blob");
  const [color, setColor] = useState(initial?.color ?? SWATCHES[0]);
  const [name, setName] = useState(initial?.name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const defaultName = SPECIES_NAMES[species];

  async function handleSave() {
    setSaving(true);
    setError(null);
    const choice: PetChoice = { species, color, name: name.trim() };
    try {
      const state = await choosePet(accessToken, choice);
      onDone(state);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al guardar. Inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="pet-picker" aria-label="Elige tu mascota">
      <p className="pet-picker-label">Elige tu especie</p>
      <div className="pet-picker-chips" role="radiogroup" aria-label="Especie">
        {SPECIES.map((sp) => (
          <button
            key={sp}
            type="button"
            role="radio"
            aria-checked={sp === species}
            aria-label={SPECIES_NAMES[sp]}
            className={`pet-chip${sp === species ? " pet-chip--selected" : ""}`}
            onClick={() => setSpecies(sp)}
          >
            <Pet species={sp} color={color} size={40} />
          </button>
        ))}
      </div>

      <p className="pet-picker-label">Color</p>
      <div className="pet-picker-swatches" role="radiogroup" aria-label="Color">
        {SWATCHES.map((hex) => (
          <button
            key={hex}
            type="button"
            role="radio"
            aria-checked={hex === color}
            aria-label={SWATCH_LABELS[hex] ?? hex}
            className={`pet-swatch${hex === color ? " pet-swatch--selected" : ""}`}
            style={{ background: hex }}
            onClick={() => setColor(hex)}
          />
        ))}
      </div>

      <label className="pet-picker-label" htmlFor="pet-name-input">
        Nombre <span className="pet-picker-hint">(opcional)</span>
      </label>
      <input
        id="pet-name-input"
        className="pet-name-input"
        type="text"
        maxLength={20}
        placeholder={defaultName}
        value={name}
        onChange={(e) => setName(e.target.value)}
        autoComplete="off"
      />

      <div className="pet-picker-preview" aria-hidden>
        <Pet species={species} color={color} size={120} interactive mood="idle" />
        <span className="pet-preview-name">{name.trim() || defaultName}</span>
      </div>

      {error !== null && <p className="pet-picker-error" role="alert">{error}</p>}

      <div className="pet-picker-actions">
        <button
          type="button"
          className="pet-picker-save"
          disabled={saving}
          onClick={handleSave}
        >
          {saving ? "Guardando…" : "Guardar"}
        </button>
        {onCancel !== undefined && (
          <button type="button" className="pet-picker-cancel" disabled={saving} onClick={onCancel}>
            Cancelar
          </button>
        )}
      </div>
    </div>
  );
}
