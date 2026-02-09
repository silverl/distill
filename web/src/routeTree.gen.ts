import { createRootRoute, createRoute, createRouter } from "@tanstack/react-router";
import { RootLayout } from "./routes/__root.js";
import Dashboard from "./routes/index.js";
import ProjectList from "./routes/projects.js";
import ProjectDetail from "./routes/projects.$name.js";
import JournalList from "./routes/journal.js";
import JournalDetail from "./routes/journal.$date.js";
import BlogList from "./routes/blog.js";
import BlogDetail from "./routes/blog.$slug.js";
import Reading from "./routes/reading.js";
import ReadingDetail from "./routes/reading.$date.js";
import Publish from "./routes/publish.js";
import Settings from "./routes/settings.js";

const rootRoute = createRootRoute({ component: RootLayout });

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: Dashboard,
});

const projectsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects",
  component: ProjectList,
});

const projectDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/projects/$name",
  component: ProjectDetail,
});

const journalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/journal",
  component: JournalList,
});

const journalDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/journal/$date",
  component: JournalDetail,
});

const blogRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/blog",
  component: BlogList,
});

const blogDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/blog/$slug",
  component: BlogDetail,
});

const readingRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reading",
  component: Reading,
});

const readingDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/reading/$date",
  component: ReadingDetail,
});

const publishRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/publish",
  component: Publish,
});

const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  component: Settings,
});

export const routeTree = rootRoute.addChildren([
  indexRoute,
  projectsRoute,
  projectDetailRoute,
  journalRoute,
  journalDetailRoute,
  blogRoute,
  blogDetailRoute,
  readingRoute,
  readingDetailRoute,
  publishRoute,
  settingsRoute,
]);
