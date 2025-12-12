import { useMemo } from "react";
import { useAppSelector } from "./useAppSelector";
import enTranslations from "../locales/en.json";
import esTranslations from "../locales/es.json";

type TranslationKey = string;
type Translations = typeof enTranslations;

const translations: Record<"en" | "es", Translations> = {
  en: enTranslations,
  es: esTranslations,
};

/**
 * Hook para obtener traducciones
 * @param key - Clave de traducción en formato "section.key" o "section.nested.key"
 * @returns Texto traducido o la clave si no se encuentra
 */
export const useTranslation = () => {
  const locale = useAppSelector((state) => state.locale.locale);

  const t = useMemo(() => {
    return (key: TranslationKey, params?: Record<string, string | number>): string => {
      const keys = key.split(".");
      let value: any = translations[locale];

      // Navegar por el objeto de traducciones
      for (const k of keys) {
        if (value && typeof value === "object" && k in value) {
          value = value[k];
        } else {
          // Si no se encuentra, intentar con inglés como fallback
          if (locale !== "en") {
            let fallbackValue: any = translations.en;
            for (const fk of keys) {
              if (fallbackValue && typeof fallbackValue === "object" && fk in fallbackValue) {
                fallbackValue = fallbackValue[fk];
              } else {
                return key; // Devolver la clave si no se encuentra
              }
            }
            value = fallbackValue;
          } else {
            return key; // Devolver la clave si no se encuentra
          }
          break;
        }
      }

      // Si el valor es un string, reemplazar parámetros si existen
      if (typeof value === "string") {
        if (params) {
          return value.replace(/\{\{(\w+)\}\}/g, (match, paramKey) => {
            return params[paramKey]?.toString() || match;
          });
        }
        return value;
      }

      return key; // Devolver la clave si el valor no es un string
    };
  }, [locale]);

  return { t, locale };
};

