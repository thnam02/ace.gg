import type { RoleMix } from "@/lib/types";

type PlayerRoleMixProps = {
  role: string | null | undefined;
  roles?: RoleMix[] | null;
};

export function roleMixItems(
  role: string | null | undefined,
  roles?: RoleMix[] | null,
): RoleMix[] {
  if (roles && roles.length > 0) {
    return roles;
  }
  if (role) {
    return [{ role, rounds: 0, share: 1, is_main: true }];
  }
  return [];
}

export function PlayerRoleMix({ role, roles }: PlayerRoleMixProps) {
  const items = roleMixItems(role, roles);
  if (items.length === 0) {
    return <span>—</span>;
  }
  const main = items.find((item) => item.is_main)?.role ?? items[0]?.role;
  const others = items.filter((item) => item.role !== main).map((item) => item.role);
  const label =
    others.length > 0
      ? `Main role ${main}, also ${others.join(", ")}`
      : `Main role ${main}`;

  return (
    <span aria-label={label}>
      {items.map((item, index) => (
        <span key={item.role}>
          {index > 0 ? <span className="text-muted-foreground"> · </span> : null}
          <span
            className={
              item.is_main ? "font-medium text-foreground" : "text-muted-foreground"
            }
          >
            {item.role}
          </span>
        </span>
      ))}
    </span>
  );
}
