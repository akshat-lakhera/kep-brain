import { PersonLink } from "@/components/ui";

export function PersonList({ people }: { people: { login: string }[] }) {
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {people.map((p) => (
        <PersonLink key={p.login} login={p.login} />
      ))}
    </span>
  );
}
