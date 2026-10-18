import type { Metadata, Route } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

export const metadata: Metadata = { title: "Page not found" };

const STICKER = "https://media.tenor.com/FORgu4-vEYIAAAAi/base-binocular.gif";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-[640px] flex-col items-center px-4 py-14 text-center md:py-20">
      <figure>
        {/* Hotlinked on purpose: the sticker is third-party, not part of this repository or its licence. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={STICKER}
          alt="Cartoon cat searching through binoculars"
          width={498}
          height={498}
          referrerPolicy="no-referrer"
          className="h-auto w-[220px] md:w-[260px]"
        />
      </figure>
      <p className="mt-7">
        <span className="eyebrow-pill">404</span>
      </p>
      <h1 className="display mt-5 text-3xl text-fg md:text-4xl">This page never made it past provisional.</h1>
      <p className="mt-4 text-lead text-fg-secondary">Not in the graph. At least its records agree.</p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link href={"/ask" as Route} className="btn btn-primary">
          Ask a real question
          <ArrowRight aria-hidden="true" size={16} strokeWidth={2} />
        </Link>
        <Link href="/explore" className="btn btn-secondary">
          Explore
        </Link>
      </div>
    </div>
  );
}
