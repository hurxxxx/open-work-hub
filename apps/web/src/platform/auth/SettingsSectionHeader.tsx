export function SettingsSectionHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-6">
      <h2 className="app-text-title-md text-app-ink">{title}</h2>
      {description ? (
        <p className="app-text-body mt-1 text-app-ink/55">{description}</p>
      ) : null}
    </div>
  );
}
