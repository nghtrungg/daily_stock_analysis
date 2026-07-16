import { DashboardPage } from '../features/dashboard/dashboard-page';
import { PortfolioProvider } from '../features/portfolio/portfolio-provider';
import { requireUser } from '../lib/auth/require-user';

export default async function HomePage() {
  await requireUser();

  return <PortfolioProvider><DashboardPage /></PortfolioProvider>;
}
