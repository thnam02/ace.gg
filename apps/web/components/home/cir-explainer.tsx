import { CaretDownIcon, CaretRightIcon } from "@phosphor-icons/react/dist/ssr";

import { CIR_STEPS, HOME_BEYOND_KD, HOME_CIR_NAME, HOME_CIR_SHORT } from "@/lib/home";

export function CirExplainer() {
  return (
    <section aria-labelledby="how-cir-heading" className="space-y-8">
      <div className="max-w-2xl">
        <h2
          id="how-cir-heading"
          className="font-sans text-2xl font-semibold tracking-tight sm:text-[28px]"
        >
          How CIR works
        </h2>
        <p className="mt-2 text-sm text-muted-foreground sm:text-base">
          <span className="font-medium text-foreground">CIR</span>
          {" · "}
          {HOME_CIR_NAME}. {HOME_CIR_SHORT}
        </p>
      </div>

      <ol className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {CIR_STEPS.map((step, index) => (
          <li key={step.title} className="min-w-0">
            <p className="font-mono text-xs tabular-nums text-muted-foreground">{index + 1}</p>
            <h3 className="mt-2 font-sans text-base font-semibold tracking-tight">{step.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
          </li>
        ))}
      </ol>

      <div className="flex flex-col items-stretch gap-2 md:flex-row md:items-center md:gap-3">
        {CIR_STEPS.map((step, index) => (
          <div key={step.chip} className="flex flex-1 flex-col items-stretch gap-2 md:flex-row md:items-center">
            <p className="rounded-md border border-white/10 bg-card px-3 py-2 text-center text-sm">
              {step.chip}
            </p>
            {index < CIR_STEPS.length - 1 ? (
              <>
                <CaretDownIcon
                  className="mx-auto size-4 text-muted-foreground md:hidden"
                  aria-hidden="true"
                />
                <CaretRightIcon
                  className="hidden size-4 shrink-0 text-muted-foreground md:block"
                  aria-hidden="true"
                />
              </>
            ) : null}
          </div>
        ))}
      </div>

      <CirExample />

      <div className="max-w-2xl">
        <h3 className="font-sans text-lg font-semibold tracking-tight">Beyond K/D and ACS</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{HOME_BEYOND_KD}</p>
      </div>
    </section>
  );
}

export function CirExample() {
  return (
    <aside
      aria-label="Illustrative CIR example"
      className="max-w-2xl rounded-xl border border-white/10 bg-card p-4 sm:p-5"
    >
      <p className="font-mono text-[11px] uppercase tracking-wide text-muted-foreground">
        Example
      </p>
      <p className="mt-1 font-sans text-sm font-medium">T1 Controller</p>
      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Actual KPR</dt>
          <dd className="font-mono tabular-nums">0.74</dd>
          <dt className="mt-2 text-muted-foreground">Expected KPR</dt>
          <dd className="font-mono tabular-nums">0.67</dd>
          <p className="mt-2 font-mono tabular-nums text-accent">+0.07</p>
        </div>
        <div>
          <dt className="text-muted-foreground">Actual DPR</dt>
          <dd className="font-mono tabular-nums">0.60</dd>
          <dt className="mt-2 text-muted-foreground">Expected DPR</dt>
          <dd className="font-mono tabular-nums">0.65</dd>
          <p className="mt-2 font-mono tabular-nums">0.05 fewer deaths/round</p>
        </div>
      </dl>
      <p className="mt-4 text-sm">
        → CIR <span className="font-mono font-semibold tabular-nums text-accent">82</span>
      </p>
    </aside>
  );
}
