export function ToastMessage({ kind, id, message }: { kind: string; id: string; message: string }) {
  return <span data-testid={`notification-${kind}-${id}`}>{message}</span>;
}
