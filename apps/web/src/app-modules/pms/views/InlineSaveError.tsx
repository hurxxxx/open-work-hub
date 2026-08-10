export function InlineSaveError({ message }: { message: string }) {
  return (
    <div className="app-text-body rounded-md border border-app-danger/20 bg-app-danger/10 px-3 py-2 text-app-danger-text">
      {message}
    </div>
  );
}
