const pulseKeyframes = `
@keyframes agent-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.3); }
}
`;

const dotStyle: Record<string, React.CSSProperties> = {
  connected: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: '#10b981',
    boxShadow: '0 0 6px rgba(16, 185, 129, 0.5)',
    animation: 'agent-pulse 2s ease-in-out infinite',
    display: 'inline-block',
    flexShrink: 0,
  },
  unreachable: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: '#f59e0b',
    display: 'inline-block',
    flexShrink: 0,
  },
  offline: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: '#7C7F88',
    display: 'inline-block',
    flexShrink: 0,
  },
  unknown: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    background: '#E3E4E8',
    border: '1px solid #7C7F88',
    display: 'inline-block',
    flexShrink: 0,
  },
};

interface AgentStatusDotProps {
  connected: boolean;
  netStatus?: 'reachable' | 'unreachable' | 'unknown';
}

export default function AgentStatusDot({ connected, netStatus }: AgentStatusDotProps) {
  return (
    <>
      <style>{pulseKeyframes}</style>
      <span
        style={
          connected
            ? dotStyle.connected
            : netStatus === 'unreachable'
              ? dotStyle.unreachable
              : netStatus === 'unknown'
                ? dotStyle.unknown
                : dotStyle.offline
        }
      />
    </>
  );
}
