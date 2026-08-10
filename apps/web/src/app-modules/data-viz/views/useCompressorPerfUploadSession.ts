import {
  useCallback,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react';

import {
  capacitiesForCategory,
  type PerfCategory,
  type PerfRefrigerant,
  type PerfSourceUploadResult,
} from '../api/dataviz-api';

export interface CompressorPerfUploadColumnSession {
  key: PerfCategory;
  master: File | null;
  setMaster: Dispatch<SetStateAction<File | null>>;
  masterRef: RefObject<HTMLInputElement | null>;
  sourceRefrigerant: PerfRefrigerant;
  setSourceRefrigerant: Dispatch<SetStateAction<PerfRefrigerant>>;
  sourceCapacity: string;
  setSourceCapacity: Dispatch<SetStateAction<string>>;
  sourceCapacities: readonly string[];
  sourceFiles: File[];
  setSourceFiles: Dispatch<SetStateAction<File[]>>;
  sourceInputRef: RefObject<HTMLInputElement | null>;
  dragging: boolean;
  setDragging: Dispatch<SetStateAction<boolean>>;
  clearMaster: () => void;
  clearSourceFiles: () => void;
}

export interface CompressorPerfUploadSession {
  columns: CompressorPerfUploadColumnSession[];
  uploadResult: PerfSourceUploadResult | null;
  setUploadResult: Dispatch<SetStateAction<PerfSourceUploadResult | null>>;
}

export function useCompressorPerfUploadSession(): CompressorPerfUploadSession {
  const [uploadResult, setUploadResult] =
    useState<PerfSourceUploadResult | null>(null);
  const [variableMaster, setVariableMaster] = useState<File | null>(null);
  const [electricMaster, setElectricMaster] = useState<File | null>(null);
  const [variableSourceFiles, setVariableSourceFiles] = useState<File[]>([]);
  const [electricSourceFiles, setElectricSourceFiles] = useState<File[]>([]);
  const [variableSourceRefrigerant, setVariableSourceRefrigerant] =
    useState<PerfRefrigerant>('new');
  const [electricSourceRefrigerant, setElectricSourceRefrigerant] =
    useState<PerfRefrigerant>('new');
  const variableCapacities = useMemo(
    () => capacitiesForCategory('variable'),
    [],
  );
  const electricCapacities = useMemo(
    () => capacitiesForCategory('electric'),
    [],
  );
  const [variableSourceCapacity, setVariableSourceCapacity] = useState(
    variableCapacities[0],
  );
  const [electricSourceCapacity, setElectricSourceCapacity] = useState(
    electricCapacities[0],
  );
  const [variableDragging, setVariableDragging] = useState(false);
  const [electricDragging, setElectricDragging] = useState(false);
  const variableMasterInputRef = useRef<HTMLInputElement | null>(null);
  const electricMasterInputRef = useRef<HTMLInputElement | null>(null);
  const variableSourceInputRef = useRef<HTMLInputElement | null>(null);
  const electricSourceInputRef = useRef<HTMLInputElement | null>(null);

  const clearVariableMaster = useCallback(() => {
    setVariableMaster(null);
    if (variableMasterInputRef.current)
      variableMasterInputRef.current.value = '';
  }, []);

  const clearElectricMaster = useCallback(() => {
    setElectricMaster(null);
    if (electricMasterInputRef.current)
      electricMasterInputRef.current.value = '';
  }, []);

  const clearVariableSourceFiles = useCallback(() => {
    setVariableSourceFiles([]);
    if (variableSourceInputRef.current)
      variableSourceInputRef.current.value = '';
  }, []);

  const clearElectricSourceFiles = useCallback(() => {
    setElectricSourceFiles([]);
    if (electricSourceInputRef.current)
      electricSourceInputRef.current.value = '';
  }, []);

  const columns = useMemo(
    () => [
      {
        key: 'variable' as const,
        master: variableMaster,
        setMaster: setVariableMaster,
        masterRef: variableMasterInputRef,
        sourceRefrigerant: variableSourceRefrigerant,
        setSourceRefrigerant: setVariableSourceRefrigerant,
        sourceCapacity: variableSourceCapacity,
        setSourceCapacity: setVariableSourceCapacity,
        sourceCapacities: variableCapacities,
        sourceFiles: variableSourceFiles,
        setSourceFiles: setVariableSourceFiles,
        sourceInputRef: variableSourceInputRef,
        dragging: variableDragging,
        setDragging: setVariableDragging,
        clearMaster: clearVariableMaster,
        clearSourceFiles: clearVariableSourceFiles,
      },
      {
        key: 'electric' as const,
        master: electricMaster,
        setMaster: setElectricMaster,
        masterRef: electricMasterInputRef,
        sourceRefrigerant: electricSourceRefrigerant,
        setSourceRefrigerant: setElectricSourceRefrigerant,
        sourceCapacity: electricSourceCapacity,
        setSourceCapacity: setElectricSourceCapacity,
        sourceCapacities: electricCapacities,
        sourceFiles: electricSourceFiles,
        setSourceFiles: setElectricSourceFiles,
        sourceInputRef: electricSourceInputRef,
        dragging: electricDragging,
        setDragging: setElectricDragging,
        clearMaster: clearElectricMaster,
        clearSourceFiles: clearElectricSourceFiles,
      },
    ],
    [
      clearElectricMaster,
      clearElectricSourceFiles,
      clearVariableMaster,
      clearVariableSourceFiles,
      electricCapacities,
      electricDragging,
      electricMaster,
      electricSourceCapacity,
      electricSourceFiles,
      electricSourceRefrigerant,
      variableCapacities,
      variableDragging,
      variableMaster,
      variableSourceCapacity,
      variableSourceFiles,
      variableSourceRefrigerant,
    ],
  );

  return { columns, uploadResult, setUploadResult };
}
