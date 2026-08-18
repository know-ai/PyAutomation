type AreaFilterProps = {
  value: string;
  areas: string[];
  onChange: (area: string) => void;
  plantLabel: string;
};

export function AreaFilter({ value, areas, onChange, plantLabel }: AreaFilterProps) {
  return (
    <select
      className="form-select form-select-sm"
      style={{ width: "150px", maxWidth: "100%" }}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      aria-label={plantLabel}
    >
      <option value="">{plantLabel}</option>
      {areas.map((area) => (
        <option key={area} value={area}>
          {area}
        </option>
      ))}
    </select>
  );
}
