// Giriş kapısı: site kilitliyse parolayı sorar. Parola doğrulanınca çözülür (Promise).
import { unlock } from "../data.js";
import { esc } from "../format.js";
import { tt } from "../i18n.js";

export function askPassword() {
  return new Promise((resolve) => {
    const gate = document.createElement("div");
    gate.className = "gate";
    gate.innerHTML = `
      <form class="gate-box" autocomplete="on">
        <svg viewBox="0 0 32 32" width="44" height="44" aria-hidden="true">
          <ellipse cx="16" cy="16" rx="12.5" ry="5" fill="none" stroke="currentColor" stroke-width="1.6" transform="rotate(-28 16 16)"/>
          <circle cx="16" cy="16" r="3.4" fill="currentColor"/>
        </svg>
        <h1>${esc(tt("gate.title"))}</h1>
        <p>${esc(tt("gate.text"))}</p>
        <label class="sr-only" for="gate-pw">${esc(tt("gate.password"))}</label>
        <input id="gate-pw" type="password" name="password" autocomplete="current-password"
               placeholder="${esc(tt("gate.password"))}" required autofocus>
        <label class="gate-remember"><input type="checkbox" name="remember" checked>${esc(tt("gate.remember"))}</label>
        <button type="submit">${esc(tt("gate.open"))}</button>
        <p class="gate-msg" role="alert" aria-live="assertive"></p>
      </form>`;
    document.body.append(gate);            // uygulamanın geri kalanı parola doğrulanana dek gizli kalır

    const form = gate.querySelector("form");
    const msg = gate.querySelector(".gate-msg");
    const btn = form.querySelector("button");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      btn.disabled = true;
      msg.textContent = tt("gate.working");
      let ok = false;
      try {
        ok = await unlock(form.elements.password.value, form.elements.remember.checked);
      } catch {
        msg.textContent = tt("gate.failed");
        btn.disabled = false;
        return;
      }
      if (!ok) {
        msg.textContent = tt("gate.wrong");
        btn.disabled = false;
        form.elements.password.select();
        return;
      }
      gate.remove();
      resolve();
    });
  });
}
