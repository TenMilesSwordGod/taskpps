import { useRoutes } from 'react-router-dom';
import AppLayout from '@/layouts/AppLayout';
import { ProjectProvider } from '@/contexts/ProjectContext';
import routes from '@/routes';

export default function App() {
  const element = useRoutes(routes);

  return (
    <ProjectProvider>
      <AppLayout>
        {element}
      </AppLayout>
    </ProjectProvider>
  );
}
