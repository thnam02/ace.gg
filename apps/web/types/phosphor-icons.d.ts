/**
 * Widen Phosphor IconProps so className/aria-hidden typecheck under React 19.2.
 */
import "@phosphor-icons/react";

declare module "@phosphor-icons/react" {
  interface IconProps {
    className?: string;
    "aria-hidden"?: boolean | "true" | "false";
  }
}

declare module "@phosphor-icons/react/dist/ssr" {
  interface IconProps {
    className?: string;
    "aria-hidden"?: boolean | "true" | "false";
  }
}

export {};
