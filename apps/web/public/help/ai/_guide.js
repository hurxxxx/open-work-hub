// Shared lightbox for AI per-feature help guides.
(() => {
  const lightbox = document.querySelector("#imageLightbox");
  if (!lightbox) return;
  const image = lightbox.querySelector(".lightbox-image");
  const title = lightbox.querySelector(".lightbox-title");
  const caption = lightbox.querySelector(".lightbox-caption");
  const closeButton = lightbox.querySelector(".lightbox-close");
  let lastActive = null;

  const close = () => {
    lightbox.hidden = true;
    image.removeAttribute("src");
    document.body.style.overflow = "";
    if (lastActive) lastActive.focus();
  };

  document.querySelectorAll("a.shot").forEach((shot) => {
    shot.addEventListener("click", (event) => {
      event.preventDefault();
      lastActive = document.activeElement;
      const img = shot.querySelector("img");
      const figure = shot.closest("figure");
      const heading = figure?.querySelector("figcaption h3")?.textContent?.trim();
      const alt = img?.getAttribute("alt") || "스크린샷";
      image.src = shot.href;
      image.alt = alt;
      title.textContent = heading || alt;
      caption.textContent = alt;
      lightbox.hidden = false;
      document.body.style.overflow = "hidden";
      closeButton.focus();
    });
  });

  closeButton.addEventListener("click", close);
  lightbox.addEventListener("click", (event) => {
    if (event.target === lightbox) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !lightbox.hidden) close();
  });
})();
