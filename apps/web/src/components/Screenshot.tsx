import Image, { type StaticImageData } from "next/image";
import { cx } from "./ui";

/**
 * A product screenshot in a thin browser frame: three dots and the page's route in mono in the title strip, a 1px
 * strong border, 14px radius, an inset highlight on the top edge and a deep drop shadow. The hero frame also sits on
 * a soft radial glow; every other frame is the same without it.
 */
export function Screenshot({
  src,
  alt,
  path,
  hero = false,
  sizes,
  className,
}: {
  src: StaticImageData;
  alt: string;
  /** The route shown in the title strip, e.g. "/ask". */
  path: string;
  hero?: boolean;
  sizes: string;
  className?: string;
}) {
  return (
    <div className={cx(hero && "frame-glow", className)}>
      <figure className="frame overflow-hidden bg-surface">
        <figcaption className="hairline flex h-9 items-center gap-3 bg-surface-subtle px-3.5">
          <span aria-hidden="true" className="flex gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
            <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
            <span className="h-2.5 w-2.5 rounded-full bg-border-strong" />
          </span>
          <span className="font-mono text-xs text-fg-muted">
            <span className="sr-only">Screenshot of </span>
            kep-brain<span aria-hidden="true">{path}</span>
            <span className="sr-only"> {path}</span>
          </span>
        </figcaption>
        <Image src={src} alt={alt} sizes={sizes} priority={hero} placeholder="blur" className="block h-auto w-full" />
      </figure>
    </div>
  );
}
