import { CONFIG } from "./config.js";
import { HttpDashboardRepository } from "./repositories/HttpDashboardRepository.js";
import { DashboardService } from "./services/DashboardService.js";
import { DashboardView } from "./views/DashboardView.js";
import { PeopleView } from "./views/PeopleView.js";
import { InsightsView } from "./views/InsightsView.js";
import { DashboardController } from "./controllers/DashboardController.js";
import { PeopleController } from "./controllers/PeopleController.js";

async function bootstrap() {
  const service = new DashboardService(new HttpDashboardRepository());
  const view = new DashboardView();
  const controller = new DashboardController(service, view);
  const people = new PeopleController({
    service, view, peopleView: new PeopleView(), insightsView: new InsightsView(),
    getStores: () => controller.data.storeList ?? [], refresh: () => controller.refresh(),
  });
  controller.registerPage("colaboradores", () => people.showPeople());
  controller.registerPage("mentoria", () => people.showMentorships());
  controller.registerPage("insights", () => people.showInsights());

  try {
    await controller.init();
    people.bind();
  } catch (error) {
    console.error("Falha ao iniciar o painel:", error);
    document.querySelector("main").innerHTML = `
      <section class="panel" style="margin:32px auto;max-width:560px">
        <h1>Não foi possível carregar o painel</h1>
        <p>${error.message}</p>
        <p>Suba o núcleo com <code>uvicorn app.main:app --port 8000</code> e abra <code>${CONFIG.apiBase}/painel/</code>.</p>
      </section>`;
  }
}

bootstrap();
