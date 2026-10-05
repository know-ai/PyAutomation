import { useEffect, useState } from "react";
import clsx from "clsx";
import { SettingsChapter } from "./SettingsChapter";
import { useTranslation } from "../hooks/useTranslation";
import { getOperatorConfirmation, putOperatorConfirmation } from "../services/operatorConfirmation";
import { showToast } from "../utils/toast";

type OperatorConfirmationPanelProps = {
  canMutate: boolean;
};

export function OperatorConfirmationPanel({ canMutate }: OperatorConfirmationPanelProps) {
  const { t } = useTranslation();
  const [enabled, setEnabled] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void getOperatorConfirmation()
      .then((policy) => {
        if (!cancelled) setEnabled(policy.enabled);
      })
      .catch(() => {
        if (!cancelled) setEnabled(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const choose = async (next: boolean) => {
    if (!canMutate || saving || next === enabled) return;
    setSaving(true);
    try {
      const saved = await putOperatorConfirmation(next);
      setEnabled(saved.enabled);
      showToast(t("settings.operatorConfirmationSaved"), "success");
    } catch (error: unknown) {
      const message = (error as { response?: { data?: { message?: string } } })?.response?.data?.message;
      showToast(message || t("settings.operatorConfirmationError"), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingsChapter
      id="settings-operator-confirmation"
      index="06"
      kicker={t("settings.operatorConfirmationKicker")}
      title={t("settings.operatorConfirmationTitle")}
      lede={t("settings.operatorConfirmationLede")}
    >
      <div className="settings-choice" role="radiogroup" aria-label={t("settings.operatorConfirmationTitle")}>
        <button
          type="button"
          role="radio"
          aria-checked={!enabled}
          className={clsx("settings-choice__card", !enabled && "is-selected")}
          disabled={!canMutate || saving}
          onClick={() => void choose(false)}
        >
          <i className="bi bi-unlock settings-choice__icon" aria-hidden="true" />
          <span className="settings-choice__copy">
            <span className="settings-choice__name">{t("settings.operatorConfirmationOff")}</span>
            <span className="settings-choice__hint">{t("settings.operatorConfirmationOffHint")}</span>
          </span>
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={enabled}
          className={clsx("settings-choice__card", enabled && "is-selected")}
          disabled={!canMutate || saving}
          onClick={() => void choose(true)}
        >
          <i className="bi bi-shield-lock settings-choice__icon" aria-hidden="true" />
          <span className="settings-choice__copy">
            <span className="settings-choice__name">{t("settings.operatorConfirmationOn")}</span>
            <span className="settings-choice__hint">{t("settings.operatorConfirmationOnHint")}</span>
          </span>
        </button>
      </div>
    </SettingsChapter>
  );
}
