from setuptools import find_packages, setup


requirements = [
    'bcolz',
    'enaml',
    'joblib',
    'json_tricks',
    'numpy',
    'palettable',
    'pyqtgraph',
    'scipy',
    'pandas',
]


extras_require = {
    'ni': ['pydaqmx'],
    'docs': ['sphinx', 'sphinx_rtd_theme', 'pygments-enaml'],
    'examples': ['matplotlib'],
    'test': ['pytest', 'pytest-benchmark'],
}


setup(
    name='psiexperiment',
    version='0.1.4.post2',
    author='Brad Buran',
    author_email='bburan@alum.mit.edu',
    install_requires=requirements,
    extras_require=extras_require,
    packages=find_packages(),
    include_package_data=True,
    license='LICENSE.txt',
    description='Module for running trial-based experiments.',
    entry_points={
        'console_scripts': [
            'psi=psi.application.psi_launcher:main',
            'psi-config=psi.application:config',
            'psi-behavior=psi.application.base_launcher:main_animal',
            'psi-calibration=psi.application.base_launcher:main_calibration',
            'psi-cfts=psi.application.base_launcher:main_ear',
            'psi-cohort=psi.application.base_launcher:main_cohort',
            'psi-summarize-abr=psi.data.io.summarize_abr:main',
            'psi-summarize-abr-gui=psi.data.io.summarize_abr:main_gui',
            'psi-summarize-abr-auto=psi.data.io.summarize_abr:main_auto',
        ]
    },
)
