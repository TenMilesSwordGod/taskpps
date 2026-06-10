import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';

interface ProjectContextValue {
  selectedProjectId: string | null;
  setSelectedProjectId: (id: string | null) => void;
}

const ProjectContext = createContext<ProjectContextValue>({
  selectedProjectId: null,
  setSelectedProjectId: () => {},
});

/** 提供选中项目 ID 的上下文 */
export function ProjectProvider({ children }: { children: ReactNode }) {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);

  const handleSet = useCallback((id: string | null) => {
    setSelectedProjectId(id);
  }, []);

  return (
    <ProjectContext.Provider value={{ selectedProjectId, setSelectedProjectId: handleSet }}>
      {children}
    </ProjectContext.Provider>
  );
}

/** 获取当前选中项目 ID */
export function useProjectId(): string | null {
  return useContext(ProjectContext).selectedProjectId;
}

/** 获取完整的 project context（含 setter） */
export function useProjectContext() {
  return useContext(ProjectContext);
}
