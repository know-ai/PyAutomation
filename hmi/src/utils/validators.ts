export const required = (value: string) => value.trim().length > 0;

export const minLength = (value: string, length: number) =>
  value.trim().length >= length;


