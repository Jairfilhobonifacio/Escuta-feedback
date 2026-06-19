"use client";

import * as React from "react";
import {
  motion,
  useReducedMotion,
  type HTMLMotionProps,
  type Variants,
} from "framer-motion";

/* ============================================================================
   Motion — helpers de entrada (framer-motion) para as telas do painel.

   <Reveal>      fade + slide-up (~16px), ease-out. Um bloco que "surge".
   <Stagger>     container que escalona a entrada dos filhos <StaggerItem>.
   <StaggerItem> item de uma lista/grid escalonada.

   Todos respeitam prefers-reduced-motion: quando o usuário pede menos movimento,
   a animação é neutralizada (aparece sem deslocamento). API simples — só
   embrulhar o conteúdo; aceita className/style e repassa props de motion.
   ========================================================================== */

const EASE_OUT = [0.22, 1, 0.36, 1] as const;
const SLIDE_Y = 16;

type RevealProps = {
  children: React.ReactNode;
  /** atraso em segundos antes de iniciar (ex.: 0.05) */
  delay?: number;
  className?: string;
} & Omit<HTMLMotionProps<"div">, "ref" | "children">;

/** Bloco que entra com fade + leve slide-up. Respeita prefers-reduced-motion. */
export function Reveal({ children, delay = 0, className, ...rest }: RevealProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: SLIDE_Y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.42, ease: EASE_OUT, delay }}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

type StaggerProps = {
  children: React.ReactNode;
  /** intervalo entre filhos, em segundos (default 0.06) */
  stagger?: number;
  /** atraso inicial do grupo, em segundos */
  delayChildren?: number;
  className?: string;
} & Omit<HTMLMotionProps<"div">, "ref" | "children">;

/** Container que escalona a entrada dos <StaggerItem> filhos. */
export function Stagger({
  children,
  stagger = 0.06,
  delayChildren = 0,
  className,
  ...rest
}: StaggerProps) {
  const reduce = useReducedMotion();
  const container: Variants = {
    hidden: {},
    show: {
      transition: reduce
        ? {}
        : { staggerChildren: stagger, delayChildren },
    },
  };
  return (
    <motion.div
      className={className}
      variants={container}
      initial="hidden"
      animate="show"
      {...rest}
    >
      {children}
    </motion.div>
  );
}

type StaggerItemProps = {
  children: React.ReactNode;
  className?: string;
} & Omit<HTMLMotionProps<"div">, "ref" | "children">;

/** Item de uma lista/grid dentro de <Stagger>. */
export function StaggerItem({ children, className, ...rest }: StaggerItemProps) {
  const reduce = useReducedMotion();
  const item: Variants = {
    hidden: reduce ? { opacity: 0 } : { opacity: 0, y: SLIDE_Y },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.42, ease: EASE_OUT },
    },
  };
  return (
    <motion.div className={className} variants={item} {...rest}>
      {children}
    </motion.div>
  );
}
