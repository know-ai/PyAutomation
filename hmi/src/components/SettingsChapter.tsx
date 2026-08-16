import clsx from "clsx";
import type { ReactNode } from "react";

type SettingsChapterProps = {
  id: string;
  index: string;
  kicker: string;
  title: string;
  lede?: string;
  children: ReactNode;
  className?: string;
};

export function SettingsChapter({
  id,
  index,
  kicker,
  title,
  lede,
  children,
  className,
}: SettingsChapterProps) {
  return (
    <section
      id={id}
      className={clsx("settings-chapter", className)}
      aria-labelledby={`${id}-title`}
    >
      <header className="settings-chapter__head">
        <span className="settings-chapter__index" aria-hidden="true">
          {index}
        </span>
        <div className="settings-chapter__intro">
          <p className="settings-kicker">{kicker}</p>
          <h3 id={`${id}-title`} className="settings-chapter__title">
            {title}
          </h3>
          {lede ? <p className="settings-chapter__lede">{lede}</p> : null}
        </div>
      </header>
      <div className="settings-chapter__body">{children}</div>
    </section>
  );
}
